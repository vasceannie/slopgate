"""Focused gates for target normalization and hot-rule recovery wording."""

from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
from typing import cast
from slopgate.constants import METADATA_PATH
from slopgate.context import build_context
from slopgate.engine import _retry
from slopgate.engine import evaluate_payload, render_output
from slopgate.models import RuleFinding, Severity
from tests import support
from tests.test_hot_rule_recommendation_gate import (
    additional_context,
    enroll_repo,
    write_payload,
)


def _manual_pretool_output(
    repo: Path, finding: RuleFinding
) -> tuple[dict[str, object], RuleFinding]:
    ctx = build_context(
        {
            "session_id": "hot-rule-manual-target",
            "cwd": str(repo),
            "hook_event_name": "PreToolUse",
            "tool_name": "ApplyPatch",
            "tool_input": {"content": "*** Update File: src/alpha.py\n"},
        }
    )
    findings = [finding]
    apply_loop_aware_steering = cast(
        Callable[[object, list[RuleFinding]], None],
        getattr(_retry, "apply_loop_aware_steering"),
    )
    apply_loop_aware_steering(ctx, findings)
    output = render_output(ctx, findings)
    assert output is not None
    return (output, finding)


def _pretool_value(output: dict[str, object], key: str) -> str:
    hook_output = support.nested_output(output, "hookSpecificOutput")
    return support.required_string(hook_output, key)


def _assert_contains_all(haystack: str, phrases: list[str]) -> None:
    missing = [phrase for phrase in phrases if phrase not in haystack]
    assert missing == []


def _assert_content_hit_metadata(rendered_finding: RuleFinding) -> None:
    expected = {
        METADATA_PATH: "content",
        "target": "content",
        "hits": ["src/alpha.py", "tests/test_alpha.py"],
    }
    mismatched = {
        key: rendered_finding.metadata.get(key)
        for key, value in expected.items()
        if rendered_finding.metadata.get(key) != value
    }
    assert mismatched == {}


def test_content_target_finding_promotes_first_metadata_hit_as_display_target(
    tmp_path: Path,
) -> None:
    enroll_repo(tmp_path)
    finding = RuleFinding(
        rule_id="PY-QUALITY-010",
        title="Repeated literal",
        severity=Severity.HIGH,
        decision="deny",
        message="Repeated literal found in patch content.",
        metadata={
            METADATA_PATH: "content",
            "target": "content",
            "hits": ["src/alpha.py", "tests/test_alpha.py"],
        },
    )
    output, rendered_finding = _manual_pretool_output(tmp_path, finding)
    _assert_contains_all(
        _pretool_value(output, "additionalContext"),
        ["target: src/alpha.py", "patch content touched: src/alpha.py"],
    )
    _assert_content_hit_metadata(rendered_finding)
    assert "PY-QUALITY-010" in _pretool_value(output, "permissionDecisionReason")


def test_repeated_thin_wrapper_denial_routes_to_recovery_playbook(
    tmp_path: Path,
) -> None:
    enroll_repo(tmp_path)
    content = "def target(value):\n    return value\n\n\ndef wrap(value):\n    return target(value)\n"
    first = evaluate_payload(write_payload(tmp_path, "src/retry_wrap.py", content))
    second = evaluate_payload(write_payload(tmp_path, "src/retry_wrap.py", content))
    support.assert_denied_by(first, "PY-CODE-013")
    support.assert_denied_by(second, "PY-CODE-013")
    context = additional_context(second)
    assert "failure class: structural" in context
    _assert_contains_all(
        context,
        [
            "Repeated deny detected",
            "load `code-hygiene-refactor`",
            "inline pass-throughs",
        ],
    )


def test_oversized_module_recovery_rejects_line_shaving(tmp_path: Path) -> None:
    enroll_repo(tmp_path)
    finding = RuleFinding(
        rule_id="PY-CODE-018",
        title="Python module too large",
        severity=Severity.HIGH,
        decision="deny",
        message="Python module is oversized.",
        metadata={METADATA_PATH: "src/large_module.py"},
    )
    first, _ = _manual_pretool_output(tmp_path, finding)
    second, _ = _manual_pretool_output(tmp_path, finding)
    assert "PY-CODE-018" in _pretool_value(first, "permissionDecisionReason")
    _assert_contains_all(
        _pretool_value(second, "additionalContext"),
        ["load `code-hygiene-refactor`", "module-to-package", "no line shaving"],
    )
