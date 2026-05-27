from __future__ import annotations

from tests.test_adapters import (
    CodexAdapter,
    RuleFinding,
    Severity,
    pytest,
    require_rendered,
    require_spec,
    test_support,
)

class TestCodexAdapterEdgeCases:
    """Codex adapter — PostToolUse severity semantics, context merging, unsupported events."""

    def test_posttool_critical_block_stops_session(self) -> None:
        """CRITICAL severity block on PostToolUse should emit continue:false
        WITHOUT decision:"block" (they conflict in Codex semantics)."""
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="CRIT-001",
                title="critical",
                severity=Severity.CRITICAL,
                decision="block",
                message="critical safety violation",
            )
        ]
        output = adapter.render_output(
            "PostToolUse",
            findings,
            decision="block",
            context=None,
            updated_input={},
        )
        rendered = require_rendered(output)
        assert rendered["continue"] is False, "CRITICAL must set continue=False"
        assert "CRIT-001" in test_support.required_string(rendered, "stopReason")
        assert "decision" not in rendered, (
            "continue:false and decision must not coexist"
        )

    def test_posttool_high_block_does_not_stop_session(self) -> None:
        """HIGH severity block on PostToolUse should NOT emit continue:false."""
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="HIGH-001",
                title="high",
                severity=Severity.HIGH,
                decision="block",
                message="non-critical issue",
            )
        ]
        output = adapter.render_output(
            "PostToolUse",
            findings,
            decision="block",
            context=None,
            updated_input={},
        )
        assert output is not None, "HIGH block must produce output"
        assert output["decision"] == "block", "HIGH block must set decision=block"
        assert "continue" not in output, "HIGH must not set continue:false"

    def test_posttool_critical_with_context(self) -> None:
        """CRITICAL PostToolUse stop should preserve additionalContext."""
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="CRIT-002",
                title="t",
                severity=Severity.CRITICAL,
                decision="block",
                message="critical",
                additional_context="also check this",
            )
        ]
        output = adapter.render_output(
            "PostToolUse",
            findings,
            decision="block",
            context="also check this",
            updated_input={},
        )
        rendered = require_rendered(output)
        assert rendered["continue"] is False, "CRITICAL must set continue=False"
        assert "decision" not in rendered, (
            "decision must not coexist with continue:false"
        )
        assert (
            test_support.required_string(require_spec(output), "additionalContext")
            == "also check this"
        )

    def test_posttool_mixed_critical_and_high(self) -> None:
        """Mixed CRITICAL + HIGH: CRITICAL wins → continue:false, no decision."""
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="HIGH-001",
                title="t",
                severity=Severity.HIGH,
                decision="block",
                message="high issue",
            ),
            RuleFinding(
                rule_id="CRIT-001",
                title="t",
                severity=Severity.CRITICAL,
                decision="block",
                message="critical issue",
            ),
        ]
        output = adapter.render_output(
            "PostToolUse",
            findings,
            decision="block",
            context=None,
            updated_input={},
        )
        rendered = require_rendered(output)
        assert rendered["continue"] is False, "CRITICAL wins: continue must be False"
        assert "CRIT-001" in test_support.required_string(rendered, "stopReason")
        assert "decision" not in rendered, "CRITICAL must suppress decision key"

    def test_pretool_deny_with_context(self) -> None:
        """Codex PreToolUse deny can include docs-supported context fields."""
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="R-001",
                title="t",
                severity=Severity.HIGH,
                decision="deny",
                message="nope",
                additional_context="try something else",
            ),
        ]
        output = adapter.render_output(
            "PreToolUse",
            findings,
            decision="deny",
            context="try something else",
            updated_input={},
        )
        spec = require_spec(output)
        assert spec["permissionDecision"] == "deny", (
            "deny must set permissionDecision=deny"
        )
        assert spec["additionalContext"] == "try something else"

    def test_pretool_only_context_no_decision(self) -> None:
        """Codex PreToolUse context-only output emits docs-supported additionalContext."""
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="CTX-001",
                title="t",
                severity=Severity.LOW,
                additional_context="check search results",
            ),
        ]
        output = adapter.render_output(
            "PreToolUse",
            findings,
            decision=None,
            context="check search results",
            updated_input={},
        )
        assert (
            test_support.required_string(require_spec(output), "additionalContext")
            == "check search results"
        )

    def test_stop_context_appended_to_reason(self) -> None:
        """Stop block + context → context merged into reason."""
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="STOP-001",
                title="t",
                severity=Severity.HIGH,
                decision="block",
                message="unfinished",
                additional_context="run tests",
            ),
        ]
        output = adapter.render_output(
            "Stop",
            findings,
            decision="block",
            context="run tests",
            updated_input={},
        )
        rendered = require_rendered(output)
        assert rendered["decision"] == "block", "Stop block must set decision=block"
        reason = test_support.required_string(rendered, "reason")
        assert "STOP-001" in reason, "rule id must appear in reason"
        assert "run tests" in reason, "context must be appended to reason"

    def test_user_prompt_block_with_context(self) -> None:
        """UserPromptSubmit block + context → both in output."""
        adapter = CodexAdapter()
        findings = [
            RuleFinding(
                rule_id="P-001",
                title="t",
                severity=Severity.HIGH,
                decision="block",
                message="api key",
                additional_context="redact first",
            ),
        ]
        output = adapter.render_output(
            "UserPromptSubmit",
            findings,
            decision="block",
            context="redact first",
            updated_input={},
        )
        rendered = require_rendered(output)
        assert rendered["decision"] == "block", (
            "UserPromptSubmit must set decision=block"
        )
        assert (
            test_support.required_string(require_spec(output), "additionalContext")
            == "redact first"
        )

    @pytest.mark.parametrize(
        "event",
        [
            "SubagentStop",
            "PostToolUseFailure",
            "TaskCompleted",
            "TeammateIdle",
            "ConfigChange",
            "Notification",
            "SubagentStart",
            "InstructionsLoaded",
            "WorktreeCreate",
            "WorktreeRemove",
            "PreCompact",
            "PostCompact",
            "Elicitation",
            "ElicitationResult",
            "SessionEnd",
            "StopFailure",
            "CwdChanged",
            "FileChanged",
            "TaskCreated",
        ],
    )
    def test_all_unsupported_codex_events(self, event: str) -> None:
        """Every Claude Code event not in CODEX_EVENTS → None."""
        adapter = CodexAdapter()
        dummy = [
            RuleFinding(
                rule_id="X",
                title="t",
                severity=Severity.HIGH,
                decision="block",
                message="m",
            )
        ]
        assert (
            adapter.render_output(
                event,
                dummy,
                decision="block",
                context=None,
                updated_input={},
            )
            is None
        ), f"{event} should return None on Codex"
