"""Quality-command output guidance for ERRORS-BASH-001."""

from __future__ import annotations

from slopgate.engine import evaluate_payload
from tests.support import BUNDLE_ROOT, finding_ids, hook_output, required_string


def _post_bash(command: str, stdout: str, stderr: str = "") -> dict[str, object]:
    return {
        "session_id": "t",
        "cwd": str(BUNDLE_ROOT),
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {
            "stdout": stdout,
            "stderr": stderr,
            "exitCode": 0,
        },
    }


def test_quality_lint_tail_output_gets_full_lint_guidance() -> None:
    payload = _post_bash(
        "cd /home/trav/repos/job-hunter && slopgate lint check 2>&1 | tail -8",
        """
✗ untested-production-code src/tui/views/dashboard.py: on_mount has no focused coverage
✗ PY-LOG-002 src/tui/views/dashboard.py: boundary lifecycle method lacks logging
Found 2 error-like quality findings.
""".strip(),
    )
    result = evaluate_payload(payload)
    message = required_string(hook_output(result), "additionalContext")

    expected_fragments = (
        "ERRORS-BASH-001",
        "quality-command output",
        "slopgate lint check --details",
        "tail-only",
    )
    missing = [fragment for fragment in expected_fragments if fragment not in message]
    assert not missing, f"missing quality-lint guidance fragments: {missing}"
    assert "Rerun the smallest failing command" not in message, (
        "quality-output guidance should not use generic rerun text"
    )
    assert "Rules:" not in message, "quality-output guidance should stay compact"


def _lint_alias_message(alias: str) -> str:
    payload = _post_bash(
        f"{alias} lint check 2>&1 | tail -8",
        """
✗ untested-production-code src/tui/views/dashboard.py: on_mount has no focused coverage
Found 1 error-like quality finding.
""".strip(),
    )
    result = evaluate_payload(payload)
    return required_string(hook_output(result), "additionalContext")


def test_vfc_lint_alias_gets_full_lint_guidance() -> None:
    message = _lint_alias_message("vfc")
    expected = ("quality-command output", "slopgate lint check --details", "tail-only")
    missing = [fragment for fragment in expected if fragment not in message]
    assert not missing, f"alias vfc missing guidance fragments: {missing}"
    assert "Rerun the smallest failing command" not in message, (
        "alias vfc should use quality-output guidance"
    )
    assert "Rules:" not in message, "alias vfc guidance should stay compact"


def test_isx_lint_alias_gets_full_lint_guidance() -> None:
    message = _lint_alias_message("isx")
    expected = ("quality-command output", "slopgate lint check --details", "tail-only")
    missing = [fragment for fragment in expected if fragment not in message]
    assert not missing, f"alias isx missing guidance fragments: {missing}"
    assert "Rerun the smallest failing command" not in message, (
        "alias isx should use quality-output guidance"
    )
    assert "Rules:" not in message, "alias isx guidance should stay compact"


def test_read_only_command_skipped() -> None:
    payload = _post_bash(
        "grep -n error src/main.py",
        "src/main.py:10: raise ValueError('error')",
    )
    result = evaluate_payload(payload)
    assert "ERRORS-BASH-001" not in finding_ids(result), (
        "read-only commands must not trigger"
    )


def test_clean_output_no_trigger() -> None:
    payload = _post_bash("npm build", "Build completed successfully.")
    result = evaluate_payload(payload)
    assert "ERRORS-BASH-001" not in finding_ids(result), "clean output must not trigger"
