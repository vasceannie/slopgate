"""QUALITY-LINT-001 response rendering regression gates."""

from __future__ import annotations
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import cast
from slopgate.adapters import get_adapter
from slopgate.context import HookContext, build_context
from slopgate.engine import evaluate_payload, render_output
from slopgate.engine import _retry
from slopgate.models import RuleFinding, Severity
from tests import support

QUALITY_LINT_FINDING = RuleFinding(
    rule_id="QUALITY-LINT-001",
    title="Touched-file lint advisory",
    severity=Severity.HIGH,
    decision="block",
    message=(
        "Touched-file lint detectors found issues for src/session.py. "
        "untested-production-code: 1, duplicate-call-sequence: 1. "
        "Repair touched files before continuing.\n"
        "Blocking lint collector details:\n"
        "[HOOK] untested-production-code\n"
        "file: src/session.py\n"
        "symbol: next_status\n\n"
        "[HOOK] duplicate-call-sequence\n"
        "file: src/session.py\n"
        "detail: calls [parse, validate], shared with src/session.py:cmd_session"
    ),
    metadata={
        "failing_collectors": [
            "untested-production-code: 1",
            "duplicate-call-sequence: 1",
        ],
        "path": "src/session.py",
        "paths": ["src/session.py"],
        "symbols": ["next_status", "add_session_parser", "cmd_session"],
    },
)


def _apply_loop_hints(ctx: HookContext, findings: list[RuleFinding]) -> None:
    apply_loop_aware_steering = cast(
        Callable[[HookContext, list[RuleFinding]], None],
        getattr(_retry, "apply_loop_aware_steering"),
    )
    apply_loop_aware_steering(ctx, findings)


def _render_posttool(
    repo: Path, findings: list[RuleFinding], *, platform: str = "claude"
) -> dict[str, object]:
    ctx = build_context(
        {
            "session_id": "quality-lint-response-rendering",
            "cwd": str(repo),
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "src/session.py"},
            "tool_response": {"filePath": "src/session.py", "success": True},
        }
    )
    _apply_loop_hints(ctx, findings)
    output = render_output(ctx, findings, adapter=get_adapter(platform))
    assert output is not None
    return output


def _hook_additional_context(output: dict[str, object]) -> str:
    hook_output = support.nested_output(output, "hookSpecificOutput")
    return support.required_string(hook_output, "additionalContext")


def _assert_quality_lint_response_names_uncovered_surface(
    response_text: str, context: str
) -> None:
    expected_fragments = (
        "src/session.py",
        "next_status",
        "add_session_parser",
        "cmd_session",
        "add or update the nearest behavior/integration tests",
        "from the repo root, run `slopgate lint check`",
    )
    missing = [
        fragment for fragment in expected_fragments if fragment not in response_text
    ]
    assert not missing, f"missing expected response fragments: {missing}"
    assert context in response_text
    assert "cd <repo-root>" not in response_text
    assert "slopgate lint check src/session.py" not in response_text


def _assert_immediate_context_precedes_advisory_context(context: str) -> None:
    ordered_fragments = (
        "PostToolUse already-mutated repair protocol",
        "Later design debt / not the immediate unblock action",
        "Feature-envy design debt can be cleaned up later",
    )
    positions = [context.index(fragment) for fragment in ordered_fragments]
    assert positions == sorted(positions)


def test_quality_lint_untested_production_hint_names_symbols_and_repo_root_lint(
    tmp_path: Path,
) -> None:
    output = _render_posttool(tmp_path, [deepcopy(QUALITY_LINT_FINDING)])
    reason = support.output_string(output, "reason")
    context = _hook_additional_context(output)
    response_text = f"{reason}\n{context}"
    assert "QUALITY-LINT-001" in reason
    _assert_quality_lint_response_names_uncovered_surface(response_text, context)


def test_quality_lint_rendering_filters_virtualenv_and_content_sentinel_paths(
    tmp_path: Path,
) -> None:
    finding = deepcopy(QUALITY_LINT_FINDING)
    finding.metadata.update(
        {
            "path": "content",
            "paths": [
                "src/session.py",
                ".venvs/job-hunter/lib/python3.12/site-packages/pkg/bad.py",
                "content",
                "patch.diff",
            ],
            "hits": [
                {"path": "content"},
                {"path": ".venvs/job-hunter/lib/python3.12/site-packages/pkg/bad.py"},
                {"path": "src/session.py"},
            ],
        }
    )
    output = _render_posttool(tmp_path, [finding])
    response_text = (
        f"{support.output_string(output, 'reason')}\n{_hook_additional_context(output)}"
    )
    expected = ("src/session.py",)
    forbidden = (".venvs/job-hunter", "site-packages", "patch.diff", "target: content")
    missing = [fragment for fragment in expected if fragment not in response_text]
    leaked = [fragment for fragment in forbidden if fragment in response_text]
    assert not missing and (not leaked), f"missing={missing} leaked={leaked}"


def test_codex_quality_lint_block_renders_decision_and_hook_context(
    tmp_path: Path,
) -> None:
    output = _render_posttool(tmp_path, [deepcopy(QUALITY_LINT_FINDING)], platform="codex")
    reason = support.output_string(output, "reason")
    context = _hook_additional_context(output)
    assert "QUALITY-LINT-001" in reason
    _assert_quality_lint_response_names_uncovered_surface(
        f"{reason}\n{context}", context
    )


def test_cursor_quality_lint_block_renders_top_level_additional_context(
    tmp_path: Path,
) -> None:
    payload = {
        "session_id": "quality-lint-cursor",
        "cwd": str(tmp_path),
        "hook_event_name": "afterFileEdit",
        "file_path": str(tmp_path / "src" / "session.py"),
        "edits": [{"old_string": "x", "new_string": "y"}],
    }
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "session.py").write_text("x = 1\n", encoding="utf-8")
    result = evaluate_payload(payload, platform="cursor")
    assert result.output is None or "permission" not in result.output
    output = _render_posttool(tmp_path, [deepcopy(QUALITY_LINT_FINDING)], platform="cursor")
    context = support.required_string(output, "additional_context")
    assert "QUALITY-LINT-001" in context
    _assert_quality_lint_response_names_uncovered_surface(context, context)


def test_blocking_quality_lint_context_precedes_and_labels_advisory_design_debt(
    tmp_path: Path,
) -> None:
    advisory = RuleFinding(
        rule_id="PY-CODE-012",
        title="Feature envy advisory",
        severity=Severity.LOW,
        message="Advisory only: do not retry the write solely for this.",
        additional_context="Feature-envy design debt can be cleaned up later.",
    )
    output = _render_posttool(tmp_path, [advisory, deepcopy(QUALITY_LINT_FINDING)])
    context = _hook_additional_context(output)
    assert "Later design debt / not the immediate unblock action" in context
    _assert_immediate_context_precedes_advisory_context(context)
