from __future__ import annotations

from tests.test_adapters import (
    OpenCodeAdapter,
    RuleFinding,
    Severity,
    require_rendered,
    support,
)


class TestOpenCodeAdapterRenderPreTool:
    """render_output for PreToolUse and PermissionRequest events."""

    def test_pretool_deny_action_block(self) -> None:
        adapter = OpenCodeAdapter()
        findings = [
            RuleFinding(
                rule_id="GIT-001",
                title="t",
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
        assert output is not None, "deny finding should produce output"
        assert output["action"] == "block", "deny should map to block action"
        assert "GIT-001" in support.required_string(output, "reason"), (
            "rule id should appear in reason"
        )

    def test_pretool_allow_with_updated_args(self) -> None:
        adapter = OpenCodeAdapter()
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
            "PreToolUse",
            findings,
            decision="allow",
            context=None,
            updated_input={"command": "echo safe"},
        )
        assert output is not None, "allow with updated_input should produce output"
        assert output["action"] == "allow", "action should be allow"
        assert output["updated_args"] == {"command": "echo safe"}, (
            "updated_args not set"
        )

    def test_pretool_context_only(self) -> None:
        adapter = OpenCodeAdapter()
        findings = [
            RuleFinding(
                rule_id="INFO-001",
                title="t",
                severity=Severity.LOW,
                additional_context="remember to test",
            )
        ]
        output = adapter.render_output(
            "PreToolUse",
            findings,
            decision=None,
            context="remember to test",
            updated_input={},
        )
        assert output is not None, "context-only finding should produce output"
        assert output["action"] == "context", "action should be context"
        assert output["context"] == "remember to test", "context value not set"

    def test_pretool_deny_with_context(self) -> None:
        """Deny output includes context when provided."""
        adapter = OpenCodeAdapter()
        findings = [
            RuleFinding(
                rule_id="R-001",
                title="t",
                severity=Severity.HIGH,
                decision="deny",
                message="blocked",
                additional_context="hint for the agent",
            ),
        ]
        output = adapter.render_output(
            "PreToolUse",
            findings,
            decision="deny",
            context="hint for the agent",
            updated_input={},
        )
        rendered = require_rendered(output)
        assert rendered["action"] == "block", "deny should produce block action"
        assert rendered["context"] == "hint for the agent", (
            "context not included in deny output"
        )
        assert "R-001" in support.required_string(rendered, "reason"), (
            "rule id should appear in reason"
        )

    def test_pretool_ask_maps_to_block(self) -> None:
        """OpenCode has no 'ask' concept; ask → block."""
        adapter = OpenCodeAdapter()
        findings = [
            RuleFinding(
                rule_id="ASK-001",
                title="t",
                severity=Severity.MEDIUM,
                decision="ask",
                message="confirm this",
            )
        ]
        output = adapter.render_output(
            "PreToolUse",
            findings,
            decision="ask",
            context=None,
            updated_input={},
        )
        assert output is not None, "ask finding should produce output"
        assert output["action"] == "block", "ask should map to block for OpenCode"

    def test_no_findings_returns_none(self) -> None:
        adapter = OpenCodeAdapter()
        output = adapter.render_output(
            "PreToolUse",
            [],
            decision=None,
            context=None,
            updated_input={},
        )
        assert output is None, "empty findings should return None"

    def test_permission_deny(self) -> None:
        adapter = OpenCodeAdapter()
        findings = [
            RuleFinding(
                rule_id="PERM-001",
                title="t",
                severity=Severity.HIGH,
                decision="deny",
                message="not allowed",
            )
        ]
        output = adapter.render_output(
            "PermissionRequest",
            findings,
            decision="deny",
            context=None,
            updated_input={},
        )
        assert output is not None, "deny on PermissionRequest should produce output"
        assert output["action"] == "block", "deny should map to block action"

    def test_permission_block_maps_to_block(self) -> None:
        adapter = OpenCodeAdapter()
        findings = [
            RuleFinding(
                rule_id="PERM-BLOCK",
                title="t",
                severity=Severity.HIGH,
                decision="block",
                message="blocked by policy",
            )
        ]
        output = adapter.render_output(
            "PermissionRequest",
            findings,
            decision="block",
            context=None,
            updated_input={},
        )
        assert output is not None, "block on PermissionRequest should produce output"
        assert output["action"] == "block"
        assert "PERM-BLOCK" in support.required_string(output, "reason")

    def test_permission_allow_with_updated_input(self) -> None:
        adapter = OpenCodeAdapter()
        findings = [
            RuleFinding(
                rule_id="MOD-001",
                title="t",
                severity=Severity.LOW,
                decision="allow",
                updated_input={"command": "echo safe"},
            ),
        ]
        output = adapter.render_output(
            "PermissionRequest",
            findings,
            decision="allow",
            context=None,
            updated_input={"command": "echo safe"},
        )
        rendered = require_rendered(output)
        assert rendered["action"] == "allow", "action should be allow"
        assert rendered["updated_args"] == {"command": "echo safe"}, (
            "updated_args not set"
        )

    def test_permission_allow_no_updated_input_returns_none(self) -> None:
        """PermissionRequest allow without updated_input → nothing to do."""
        adapter = OpenCodeAdapter()
        findings = [
            RuleFinding(
                rule_id="X", title="t", severity=Severity.LOW, decision="allow"
            ),
        ]
        assert (
            adapter.render_output(
                "PermissionRequest",
                findings,
                decision="allow",
                context=None,
                updated_input={},
            )
            is None
        ), "allow without updated_input should return None"
