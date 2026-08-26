"""OpenCode repair state preserves paths supplied without file content."""

from __future__ import annotations

from pathlib import Path

from slopgate.constants import BLOCK, PLATFORM_OPENCODE
from slopgate.context import HookContext, build_context
from slopgate.engine._evaluation import _record_opencode_repair_required
from slopgate.models import RuleFinding, Severity


def _path_only_context(tmp_path: Path) -> tuple[HookContext, Path]:
    source_path = tmp_path / "src" / "app.py"
    source_path.parent.mkdir()
    source_path.write_text("value = 1\n", encoding="utf-8")
    context = build_context(
        {
            "cwd": str(tmp_path),
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(source_path)},
            "execution_outcome": "returned",
            "session_id": "session-1",
            "call_id": "call-1",
        }
    )

    return context, source_path


def test_file_edited_repair_state_records_candidate_path_without_content(
    tmp_path: Path,
) -> None:
    context, source_path = _path_only_context(tmp_path)

    assert context.content_targets == [], "test must cover path-only evidence"
    assert context.candidate_paths == [str(source_path)], (
        "path-only OpenCode evidence must remain discoverable"
    )


def test_file_edited_repair_state_records_candidate_path_in_repair_state(
    tmp_path: Path,
) -> None:
    context, source_path = _path_only_context(tmp_path)

    _record_opencode_repair_required(
        context,
        [
            RuleFinding(
                rule_id="PY-AST-001",
                title="parse failure",
                severity=Severity.CRITICAL,
                decision=BLOCK,
            )
        ],
        PLATFORM_OPENCODE,
    )

    required = context.state.get_repair_required()
    assert required is not None, "blocking findings must create repair state"
    assert required["paths"] == [str(source_path)], (
        "repair verification must receive the affected file path"
    )
