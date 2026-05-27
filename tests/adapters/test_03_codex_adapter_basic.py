from __future__ import annotations

from tests.test_adapters import (
    CodexAdapter,
    RuleFinding,
    Severity,
    require_nested,
    require_rendered,
    require_spec,
    test_support,
)

class TestCodexAdapterBasic:
    """Codex adapter — normalize, core pretool/stop/session/posttool events."""

    def test_normalize_is_passthrough(self) -> None:
        adapter = CodexAdapter()
        raw = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "cwd": "/tmp",
            "session_id": "s1",
            "turn_id": "t1",
            "model": "gpt-5.4",
        }
        canonical = adapter.normalize_payload(raw)
        assert canonical is raw  # Codex format is already canonical

    def test_pretool_deny(self) -> None:
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="GIT-001",
                title="No --no-verify",
                severity=Severity.HIGH,
                decision="deny",
                message="hook bypass detected",
            )
        ]
        output = adapter.render_output(
            "PreToolUse",
            findings,
            decision="deny",
            context=None,
            updated_input={},
        )
        spec = require_spec(output)
        assert spec["hookEventName"] == "PreToolUse", "Codex must echo hookEventName"
        assert spec["permissionDecision"] == "deny", (
            "deny must set permissionDecision=deny"
        )
        assert "GIT-001" in test_support.required_string(
            spec, "permissionDecisionReason"
        )

    def test_pretool_deny_preserves_context_but_not_updated_input(self) -> None:
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="GIT-CTX",
                title="t",
                severity=Severity.HIGH,
                decision="deny",
                message="blocked",
                additional_context="use a safer command",
            )
        ]
        output = adapter.render_output(
            "PreToolUse",
            findings,
            decision="deny",
            context="use a safer command",
            updated_input={"command": "echo rewritten"},
        )
        spec = require_spec(output)
        assert spec["permissionDecision"] == "deny"
        assert spec["additionalContext"] == "use a safer command"
        assert "updatedInput" not in spec

    def test_pretool_allow_can_rewrite_input(self) -> None:
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="SAFE-REWRITE",
                title="t",
                severity=Severity.LOW,
                decision="allow",
                additional_context="command normalized",
            )
        ]
        output = adapter.render_output(
            "PreToolUse",
            findings,
            decision="allow",
            context="command normalized",
            updated_input={"command": "echo rewritten"},
        )
        spec = require_spec(output)
        assert spec["permissionDecision"] == "allow"
        assert spec["updatedInput"] == {"command": "echo rewritten"}
        assert spec["additionalContext"] == "command normalized"

    def test_pretool_block_maps_to_deny(self) -> None:
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="SYS-001",
                title="t",
                severity=Severity.HIGH,
                decision="block",
                message="system path",
            )
        ]
        output = adapter.render_output(
            "PreToolUse",
            findings,
            decision="block",
            context=None,
            updated_input={},
        )
        spec = require_spec(output)
        assert spec["permissionDecision"] == "deny", (
            "block must map to deny for Codex PreToolUse"
        )

    def test_permission_request_block_maps_to_deny(self) -> None:
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="PERM-001",
                title="t",
                severity=Severity.HIGH,
                decision="block",
                message="approval request blocked",
            )
        ]
        output = adapter.render_output(
            "PermissionRequest",
            findings,
            decision="block",
            context=None,
            updated_input={},
        )
        inner = require_nested(require_spec(output), "decision")
        assert inner["behavior"] == "deny"
        assert "PERM-001" in test_support.required_string(inner, "message")

    def test_permission_request_allow(self) -> None:
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="PERM-ALLOW",
                title="t",
                severity=Severity.LOW,
                decision="allow",
            )
        ]
        output = adapter.render_output(
            "PermissionRequest",
            findings,
            decision="allow",
            context=None,
            updated_input={"command": "echo safe"},
        )
        inner = require_nested(require_spec(output), "decision")
        assert inner == {"behavior": "allow"}

    def test_stop_block(self) -> None:
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="STOP-001",
                title="t",
                severity=Severity.HIGH,
                decision="block",
                message="review issues",
            )
        ]
        output = adapter.render_output(
            "Stop",
            findings,
            decision="block",
            context=None,
            updated_input={},
        )
        rendered = require_rendered(output)
        assert rendered["decision"] == "block", "Stop block must set decision=block"
        assert "STOP-001" in test_support.required_string(rendered, "reason")

    def test_session_start_context(self) -> None:
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="CTX-001",
                title="t",
                severity=Severity.LOW,
                additional_context="workspace conventions",
            )
        ]
        output = adapter.render_output(
            "SessionStart",
            findings,
            decision=None,
            context="workspace conventions",
            updated_input={},
        )
        assert "workspace conventions" in test_support.required_string(
            require_spec(output), "additionalContext"
        )

    def test_user_prompt_submit_block(self) -> None:
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="PROMPT-001",
                title="t",
                severity=Severity.HIGH,
                decision="block",
                message="api key detected",
            )
        ]
        output = adapter.render_output(
            "UserPromptSubmit",
            findings,
            decision="block",
            context=None,
            updated_input={},
        )
        assert output is not None, "UserPromptSubmit block must produce output"
        assert output["decision"] == "block", (
            "UserPromptSubmit block must set decision=block"
        )

    def test_posttool_context(self) -> None:
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="Q-001",
                title="t",
                severity=Severity.MEDIUM,
                additional_context="files were updated",
            )
        ]
        output = adapter.render_output(
            "PostToolUse",
            findings,
            decision=None,
            context="files were updated",
            updated_input={},
        )
        assert "files were updated" in test_support.required_string(
            require_spec(output), "additionalContext"
        )

    def test_unsupported_event_returns_none(self) -> None:
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="X-001",
                title="t",
                severity=Severity.HIGH,
                decision="deny",
                message="blocked",
            )
        ]
        # SubagentStop doesn't exist in Codex
        output = adapter.render_output(
            "SubagentStop",
            findings,
            decision="block",
            context=None,
            updated_input={},
        )
        assert output is None, "SubagentStop must return None on Codex"

    def test_no_findings_returns_none(self) -> None:
        adapter = CodexAdapter()
        output = adapter.render_output(
            "PreToolUse",
            [],
            decision=None,
            context=None,
            updated_input={},
        )
        assert output is None
