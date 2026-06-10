from __future__ import annotations

from tests.test_adapters import (
    ADAPTERS,
    ClaudeAdapter,
    CodexAdapter,
    OpenCodeAdapter,
    RuleFinding,
    Severity,
    get_adapter,
    pytest,
    require_nested,
    require_rendered,
    require_spec,
    support,
)


class TestAdapterRegistry:
    def test_all_platforms_registered(self) -> None:
        assert "claude" in ADAPTERS, "claude adapter must be registered"
        assert "codex" in ADAPTERS, "codex adapter must be registered"
        assert "opencode" in ADAPTERS, "opencode adapter must be registered"

    def test_get_adapter_returns_correct_type(self) -> None:
        assert isinstance(get_adapter("claude"), ClaudeAdapter), (
            "claude must return ClaudeAdapter"
        )
        assert isinstance(get_adapter("codex"), CodexAdapter), (
            "codex must return CodexAdapter"
        )
        assert isinstance(get_adapter("opencode"), OpenCodeAdapter), (
            "opencode must return OpenCodeAdapter"
        )

    def test_unknown_platform_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown platform"):
            _ = get_adapter("vim")


class TestClaudeAdapterBasic:
    """Claude adapter — core event rendering (normalize, pretool, permission, stop)."""

    def test_normalize_is_passthrough(self) -> None:
        adapter = ClaudeAdapter()
        raw = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": "/tmp"}
        assert adapter.normalize_payload(raw) == raw

    def test_pretool_deny(self) -> None:
        adapter = ClaudeAdapter()
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
        assert spec["permissionDecision"] == "deny", (
            "PreToolUse deny must set permissionDecision=deny"
        )
        assert "GIT-001" in support.required_string(
            spec, "permissionDecisionReason"
        )

    def test_permission_request_deny(self) -> None:
        adapter = ClaudeAdapter()
        findings = [
            RuleFinding(
                rule_id="TEST-001",
                title="t",
                severity=Severity.HIGH,
                decision="deny",
                message="blocked",
            )
        ]
        output = adapter.render_output(
            "PermissionRequest",
            findings,
            decision="deny",
            context=None,
            updated_input={},
        )
        inner = require_nested(require_spec(output), "decision")
        assert inner["behavior"] == "deny", (
            "PermissionRequest deny must set behavior=deny"
        )
        assert "TEST-001" in support.required_string(inner, "message")

    def test_stop_block(self) -> None:
        adapter = ClaudeAdapter()
        findings = [
            RuleFinding(
                rule_id="STOP-001",
                title="t",
                severity=Severity.HIGH,
                decision="block",
                message="check issues",
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
        assert "STOP-001" in support.required_string(rendered, "reason")

    def test_session_start_context(self) -> None:
        adapter = ClaudeAdapter()
        findings = [
            RuleFinding(
                rule_id="CTX-001",
                title="t",
                severity=Severity.LOW,
                additional_context="load conventions",
            )
        ]
        output = adapter.render_output(
            "SessionStart",
            findings,
            decision=None,
            context="load conventions",
            updated_input={},
        )
        assert (
            support.required_string(require_spec(output), "additionalContext")
            == "load conventions"
        )

    def test_task_completed_block(self) -> None:
        adapter = ClaudeAdapter()
        findings = [
            RuleFinding(
                rule_id="TC-001",
                title="t",
                severity=Severity.HIGH,
                decision="block",
                message="not done",
            )
        ]
        output = adapter.render_output(
            "TaskCompleted",
            findings,
            decision="block",
            context=None,
            updated_input={},
        )
        assert output is None, (
            "TaskCompleted quality-gate blocks must use Claude retry feedback "
            "via CLI exit 2 + stderr, not JSON continue:false"
        )

    def test_pretool_block_maps_to_deny(self) -> None:
        """Engine uses 'block' internally; Claude Code expects 'deny' for PreToolUse."""
        adapter = ClaudeAdapter()
        findings = [
            RuleFinding(
                rule_id="SYS-001",
                title="t",
                severity=Severity.HIGH,
                decision="block",
                message="system path blocked",
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
        # "block" → "deny" in Claude Code output
        assert spec["permissionDecision"] == "deny", (
            "block must map to deny for PreToolUse"
        )
        assert "SYS-001" in support.required_string(
            spec, "permissionDecisionReason"
        )

    def test_pretool_deny_with_context_and_updated_input(self) -> None:
        """All three fields (decision, context, updatedInput) in one output."""
        adapter = ClaudeAdapter()
        findings = [
            RuleFinding(
                rule_id="X-001",
                title="t",
                severity=Severity.HIGH,
                decision="deny",
                message="nope",
                additional_context="policy says no",
                updated_input={"command": "echo safe"},
            )
        ]
        output = adapter.render_output(
            "PreToolUse",
            findings,
            decision="deny",
            context="policy says no",
            updated_input={"command": "echo safe"},
        )
        spec = require_spec(output)
        assert spec["permissionDecision"] == "deny", "decision must be deny"
        assert spec["additionalContext"] == "policy says no", "context must be included"
        assert spec["updatedInput"] == {"command": "echo safe"}, (
            "updatedInput must be included"
        )

    def test_permission_request_allow_with_updated_input(self) -> None:
        adapter = ClaudeAdapter()
        findings = [
            RuleFinding(
                rule_id="MOD-001",
                title="t",
                severity=Severity.LOW,
                decision="allow",
                updated_input={"command": "echo safe"},
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
        assert inner["behavior"] == "allow", (
            "PermissionRequest allow must set behavior=allow"
        )
        assert inner["updatedInput"] == {"command": "echo safe"}, (
            "updatedInput must be forwarded"
        )
        assert "message" not in inner  # message is for deny only
