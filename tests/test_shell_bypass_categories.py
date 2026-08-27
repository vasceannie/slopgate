"""Tests for SHELL-001 bypass-category identification and safe replacement.

Each configured bypass pattern must record a safe category label in metadata
and render exactly one category-specific replacement scaffold that begins
with STOP and forbids equivalent-syntax retries.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from tests import support
from tests.support import BUNDLE_ROOT, finding_ids
from slopgate.engine import evaluate_payload
from slopgate.models import RuleFinding


def bash_payload(command: str) -> dict[str, object]:
    return {
        "session_id": "t",
        "cwd": str(BUNDLE_ROOT),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


def unique_bash_payload(command: str) -> dict[str, object]:
    payload = bash_payload(command)
    payload["session_id"] = f"shell-category-{uuid4().hex}"
    return payload


def shell_finding(command: str) -> RuleFinding:
    result = evaluate_payload(unique_bash_payload(command))
    shell = [f for f in result.findings if f.rule_id == "SHELL-001"]
    assert len(shell) == 1, f"expected exactly one SHELL-001 finding for: {command!r}"
    return shell[0]


class TestShellBypassCategoryGuidance:
    """SHELL-001 names the matched bypass category and one safe replacement."""

    @pytest.mark.parametrize(
        ("command", "expected_category"),
        [
            ("set +e && make build", "set_plus_e"),
            ("make build 2>/dev/null", "stderr_suppression"),
            ("Get-ChildItem -ErrorAction SilentlyContinue", "powershell_silent"),
            ("$ErrorActionPreference = 'SilentlyContinue'", "powershell_silent"),
            ("Invoke-Build *> $null", "null_redirect"),
            ("Invoke-Build | Out-Null", "null_redirect"),
            ("make build || true", "or_true"),
            ("make build || :", "or_colon"),
        ],
        ids=[
            "set_plus_e",
            "stderr_suppression",
            "powershell_param",
            "powershell_preference",
            "null_redirect",
            "out_null",
            "or_true",
            "or_colon",
        ],
    )
    def test_bypass_records_safe_category_metadata(
        self, command: str, expected_category: str
    ) -> None:
        finding = shell_finding(command)

        assert finding.decision == "deny", (
            f"SHELL-001 must deny bypass command: {command!r}"
        )
        assert finding.metadata.get("category") == expected_category, (
            f"expected category {expected_category!r}, "
            f"got {finding.metadata.get('category')!r} for {command!r}"
        )

    @pytest.mark.parametrize(
        ("command", "own_marker", "foreign_marker"),
        [
            (
                "make build 2>/dev/null",
                "if output=$(command 2>&1)",
                "command_that_might_fail",
            ),
            (
                "set +e && make build",
                "command_that_might_fail",
                "if output=$(command 2>&1)",
            ),
            (
                "make build || true",
                "documented expected failure",
                "if output=$(command 2>&1)",
            ),
        ],
        ids=["stderr_only", "set_plus_e_only", "or_true_only"],
    )
    def test_message_renders_only_the_matched_category_scaffold(
        self, command: str, own_marker: str, foreign_marker: str
    ) -> None:
        finding = shell_finding(command)
        message = finding.message or ""

        assert message.startswith("STOP"), (
            f"SHELL-001 message must start with STOP, got: {message!r}"
        )
        assert "Do not retry equivalent" in message, (
            f"message must forbid equivalent retries, got: {message!r}"
        )
        assert own_marker in message, (
            f"message must include matched-category scaffold, got: {message!r}"
        )
        assert foreign_marker not in message, (
            f"message must not leak foreign-category scaffold, got: {message!r}"
        )

    def test_metadata_records_only_safe_category_label(self) -> None:
        command = "make build 2>/dev/null"

        finding = shell_finding(command)
        dumped_metadata = json.dumps(finding.metadata)

        assert finding.metadata.get("category") == "stderr_suppression", (
            f"expected safe category label, got: {finding.metadata!r}"
        )
        assert command not in dumped_metadata, (
            f"metadata must not echo command content: {dumped_metadata!r}"
        )
        assert "build" not in dumped_metadata, (
            f"metadata must not echo command fragments: {dumped_metadata!r}"
        )

    def test_stderr_pipe_into_filter_remains_allowed(self) -> None:
        result = evaluate_payload(
            unique_bash_payload("cat build.log 2>/dev/null | grep -c error")
        )

        assert "SHELL-001" not in finding_ids(result), (
            "piped stderr suppression must stay allowed by SHELL-001"
        )

    def test_claude_reason_carries_category_scaffold(self) -> None:
        result = evaluate_payload(unique_bash_payload("make build 2>/dev/null"))
        support.assert_denied_by(result, "SHELL-001")
        reason = support.required_string(
            support.hook_output(result), "permissionDecisionReason"
        )

        assert "STOP" in reason, f"reason must carry STOP guidance: {reason!r}"
        assert "if output=$(command 2>&1)" in reason, (
            f"reason must carry stderr scaffold: {reason!r}"
        )
        assert "command_that_might_fail" not in reason, (
            f"reason must not leak set+e scaffold: {reason!r}"
        )

    def test_opencode_reason_carries_category_scaffold(self) -> None:
        result = evaluate_payload(
            unique_bash_payload("make build 2>/dev/null"), platform="opencode"
        )
        output = support.require_output(result)
        reason = support.output_string(output, "reason")

        assert "STOP" in reason, f"opencode reason must carry STOP: {reason!r}"
        assert "if output=$(command 2>&1)" in reason, (
            f"opencode reason must carry stderr scaffold: {reason!r}"
        )
        assert "command_that_might_fail" not in reason, (
            f"opencode reason must not leak set+e scaffold: {reason!r}"
        )
