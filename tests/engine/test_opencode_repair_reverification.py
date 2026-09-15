"""Repair targets recorded before their file exists stay re-verifiable."""

from __future__ import annotations

from pathlib import Path

from slopgate._types import ObjectDict, object_dict_list
from slopgate.constants import BLOCK, PLATFORM_OPENCODE
from slopgate.context import build_context
from slopgate.engine._evaluation import _record_opencode_repair_required
from slopgate.models import RuleFinding, Severity

EVENT_RELATIVE_PATH = "app.py"
NOT_EXISTING_FILE_ERROR = "finding path is not an existing file"


def _record_missing_target_from_nested_cwd(
    tmp_path: Path,
) -> tuple[ObjectDict | None, Path]:
    worktree = tmp_path / "worktree"
    event_cwd = worktree / "packages" / "service"
    event_cwd.mkdir(parents=True)
    context = build_context(
        {
            "cwd": str(event_cwd),
            "worktree": str(worktree),
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "execution_outcome": "returned",
            "session_id": "session-1",
            "call_id": "call-1",
        }
    )
    finding = RuleFinding(
        rule_id="PY-AST-001",
        title="parse failure",
        severity=Severity.CRITICAL,
        decision=BLOCK,
        metadata={"path": EVENT_RELATIVE_PATH, "function": "parse_source"},
    )
    _record_opencode_repair_required(context, [finding], PLATFORM_OPENCODE)
    return context.state.get_repair_required(), event_cwd / EVENT_RELATIVE_PATH


def test_missing_target_keeps_resolved_candidate_for_reverification(
    tmp_path: Path,
) -> None:
    required, intended = _record_missing_target_from_nested_cwd(tmp_path)

    assert required is not None, "missing targets must remain pending"
    targets = object_dict_list(required.get("targets"))
    assert targets[0]["path"] == str(intended.resolve()), (
        "the event-cwd candidate must survive record time for re-verification"
    )
    assert targets[0]["error"] == NOT_EXISTING_FILE_ERROR, (
        "the record-time failure must stay explicit in repair state"
    )
