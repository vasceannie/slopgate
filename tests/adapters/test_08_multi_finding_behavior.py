from __future__ import annotations

from tests.test_adapters import (
    Callable,
    ClaudeAdapter,
    CodexAdapter,
    ObjectDict,
    OpenCodeAdapter,
    RuleFinding,
    Severity,
    cast,
    engine_module,
    require_rendered,
    require_spec,
    test_support,
)

class TestMultiFindingBehavior:
    """Test what happens when the engine produces multiple findings with
    mixed decisions, and the adapter has to render a coherent output.

    These tests go through the full engine render_output path
    (decision priority, context merging, updated_input merging)
    into each adapter.
    """

    def _make_findings(self) -> list[RuleFinding]:
        """Three findings: deny (HIGH), allow (LOW), context-only (MEDIUM)."""
        return [
            RuleFinding(
                rule_id="DENY-001",
                title="t",
                severity=Severity.HIGH,
                decision="deny",
                message="blocked by policy",
            ),
            RuleFinding(
                rule_id="ALLOW-001",
                title="t",
                severity=Severity.LOW,
                decision="allow",
                updated_input={"command": "safe"},
            ),
            RuleFinding(
                rule_id="CTX-001",
                title="t",
                severity=Severity.MEDIUM,
                additional_context="extra context here",
            ),
        ]

    @staticmethod
    def _render_inputs(
        findings: list[RuleFinding],
    ) -> tuple[str | None, str | None, ObjectDict]:
        decision = cast(
            Callable[[list[RuleFinding]], str | None],
            getattr(engine_module, "_top_decision"),
        )(findings)
        context = cast(
            Callable[[list[RuleFinding]], str | None],
            getattr(engine_module, "_collect_context"),
        )(findings)
        updated = cast(
            Callable[[list[RuleFinding]], ObjectDict],
            getattr(engine_module, "_merge_updated_input"),
        )(findings)
        return decision, context, updated

    def test_claude_deny_wins_over_allow(self) -> None:
        """With mixed deny+allow, Claude adapter should deny (highest priority)."""
        findings = self._make_findings()
        decision, context, updated = self._render_inputs(findings)

        adapter = ClaudeAdapter()
        output = adapter.render_output(
            "PreToolUse",
            findings,
            decision=decision,
            context=context,
            updated_input=updated,
        )
        spec = require_spec(output)
        # Deny wins
        assert spec["permissionDecision"] == "deny", "deny should win over allow"
        assert "DENY-001" in test_support.required_string(
            spec, "permissionDecisionReason"
        ), "DENY-001 should appear in reason"
        # Context still included
        assert spec["additionalContext"] == "extra context here", (
            "context should be included"
        )
        # Updated input still included (forward-looking)
        assert spec["updatedInput"] == {"command": "safe"}, (
            "updated input should be included"
        )

    def test_codex_deny_wins_over_allow(self) -> None:
        findings = self._make_findings()
        decision, context, updated = self._render_inputs(findings)

        adapter = CodexAdapter()
        output = adapter.render_output(
            "PreToolUse",
            findings,
            decision=decision,
            context=context,
            updated_input=updated,
        )
        spec = require_spec(output)
        assert spec["permissionDecision"] == "deny", "Codex deny should win over allow"
        assert "DENY-001" in test_support.required_string(
            spec, "permissionDecisionReason"
        ), "DENY-001 should appear in reason"

    def test_opencode_deny_wins_over_allow(self) -> None:
        findings = self._make_findings()
        decision, context, updated = self._render_inputs(findings)

        adapter = OpenCodeAdapter()
        output = adapter.render_output(
            "PreToolUse",
            findings,
            decision=decision,
            context=context,
            updated_input=updated,
        )
        rendered = require_rendered(output)
        assert rendered["action"] == "block", (
            "OpenCode deny should produce block action"
        )
        assert "DENY-001" in test_support.required_string(rendered, "reason"), (
            "DENY-001 should appear in reason"
        )
        # Context included despite block
        assert rendered["context"] == "extra context here", (
            "context should be included with block"
        )

    def test_context_deduplication(self) -> None:
        """Identical context strings should be deduplicated."""
        findings = [
            RuleFinding(
                rule_id="A",
                title="t",
                severity=Severity.LOW,
                additional_context="same thing",
            ),
            RuleFinding(
                rule_id="B",
                title="t",
                severity=Severity.LOW,
                additional_context="same thing",
            ),
            RuleFinding(
                rule_id="C",
                title="t",
                severity=Severity.LOW,
                additional_context="different thing",
            ),
        ]
        context = cast(
            Callable[[list[RuleFinding]], str | None],
            getattr(engine_module, "_collect_context"),
        )(findings)
        assert context == "same thing\n\ndifferent thing"

    def test_updated_input_last_write_wins(self) -> None:
        """When multiple findings set the same key, last one wins."""
        findings = [
            RuleFinding(
                rule_id="A",
                title="t",
                severity=Severity.LOW,
                updated_input={"command": "first"},
            ),
            RuleFinding(
                rule_id="B",
                title="t",
                severity=Severity.LOW,
                updated_input={"command": "second", "extra": "value"},
            ),
        ]
        merged = cast(
            Callable[[list[RuleFinding]], ObjectDict],
            getattr(engine_module, "_merge_updated_input"),
        )(findings)
        assert merged == {"command": "second", "extra": "value"}
