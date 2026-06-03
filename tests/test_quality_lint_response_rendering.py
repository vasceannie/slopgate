"""QUALITY-LINT-001 response rendering regression gates."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from vibeforcer.context import HookContext, build_context
from vibeforcer.engine import render_output
from vibeforcer.engine import _retry as engine_retry
from vibeforcer.models import RuleFinding, Severity

from tests import support as test_support


def _posttool_context(repo: Path) -> HookContext:
    return build_context(
        {
            "session_id": "quality-lint-response-rendering",
            "cwd": str(repo),
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "src/session.py"},
            "tool_response": {"filePath": "src/session.py", "success": True},
        }
    )


def _apply_loop_hints(ctx: HookContext, findings: list[RuleFinding]) -> None:
    apply_loop_aware_steering = cast(
        Callable[[HookContext, list[RuleFinding]], None],
        getattr(engine_retry, "_apply_loop_aware_steering"),
    )
    apply_loop_aware_steering(ctx, findings)


def _quality_lint_finding() -> RuleFinding:
    return RuleFinding(
        rule_id="QUALITY-LINT-001",
        title="Touched-file lint advisory",
        severity=Severity.HIGH,
        decision="block",
        message=(
            "Touched-file lint detectors found issues for src/session.py. "
            "untested-production-code: 1. Repair touched files before continuing."
        ),
        metadata={
            "failing_collectors": ["untested-production-code: 1"],
            "path": "src/session.py",
            "paths": ["src/session.py"],
            "symbols": ["next_status", "add_session_parser", "cmd_session"],
        },
    )


def _render_posttool(repo: Path, findings: list[RuleFinding]) -> dict[str, object]:
    ctx = _posttool_context(repo)
    _apply_loop_hints(ctx, findings)
    output = render_output(ctx, findings)
    assert output is not None
    return output


def _hook_additional_context(output: dict[str, object]) -> str:
    hook_output = test_support.nested_output(output, "hookSpecificOutput")
    return test_support.required_string(hook_output, "additionalContext")


def _assert_quality_lint_response_names_uncovered_surface(
    response_text: str, context: str
) -> None:
    expected_fragments = (
        "src/session.py",
        "next_status",
        "add_session_parser",
        "cmd_session",
        "add or update the nearest behavior/integration tests",
        "from the repo root, run `vibeforcer lint check`",
    )
    missing = [fragment for fragment in expected_fragments if fragment not in response_text]
    assert not missing, f"missing expected response fragments: {missing}"
    assert context in response_text
    assert "cd <repo-root>" not in response_text
    assert "vibeforcer lint check src/session.py" not in response_text


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
    output = _render_posttool(tmp_path, [_quality_lint_finding()])
    reason = test_support.output_string(output, "reason")
    context = _hook_additional_context(output)

    response_text = f"{reason}\n{context}"
    assert "QUALITY-LINT-001" in reason
    _assert_quality_lint_response_names_uncovered_surface(response_text, context)


def test_quality_lint_rendering_filters_virtualenv_and_content_sentinel_paths(
    tmp_path: Path,
) -> None:
    finding = _quality_lint_finding()
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
        f"{test_support.output_string(output, 'reason')}\n"
        f"{_hook_additional_context(output)}"
    )

    expected = ("src/session.py",)
    forbidden = (
        ".venvs/job-hunter",
        "site-packages",
        "patch.diff",
        "target: content",
    )
    missing = [fragment for fragment in expected if fragment not in response_text]
    leaked = [fragment for fragment in forbidden if fragment in response_text]
    assert not missing and not leaked, f"missing={missing} leaked={leaked}"


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
    output = _render_posttool(tmp_path, [advisory, _quality_lint_finding()])

    context = _hook_additional_context(output)
    assert "Later design debt / not the immediate unblock action" in context
    _assert_immediate_context_precedes_advisory_context(context)
