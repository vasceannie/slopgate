from __future__ import annotations

from tests.test_adapters import (
    ClaudeAdapter,
    RuleFinding,
    Severity,
    pytest,
    require_nested,
    require_rendered,
    require_spec,
    support,
)


class TestClaudeAdapterEdgeCases:
    """Claude adapter — edge cases: failures, context-only, unknown events."""

    def test_subagent_start_renders_hook_specific_permission(self) -> None:
        adapter = ClaudeAdapter()
        finding = RuleFinding(
            rule_id="SUB-001",
            title="blocked",
            severity=Severity.HIGH,
            decision="deny",
            message="Subagent blocked.",
        )
        output = require_rendered(
            adapter.render_output("SubagentStart", [finding], decision="deny"),
        )
        specific = require_nested(output, "hookSpecificOutput")
        assert {
            "hookEventName": specific["hookEventName"],
            "permissionDecision": specific["permissionDecision"],
        } == {
            "hookEventName": "SubagentStart",
            "permissionDecision": "deny",
        }

    def test_permission_request_block_maps_to_deny(self) -> None:
        """Engine can escalate to block; PermissionRequest must fail closed."""
        adapter = ClaudeAdapter()
        findings = [
            RuleFinding(
                rule_id="X",
                title="t",
                severity=Severity.HIGH,
                decision="block",
                message="m",
            )
        ]
        inner = require_nested(
            require_spec(
                adapter.render_output(
                    "PermissionRequest",
                    findings,
                    decision="block",
                    context=None,
                    updated_input={},
                )
            ),
            "decision",
        )
        assert inner["behavior"] == "deny"
        assert "X" in support.required_string(inner, "message")

    def test_posttool_use_failure_advisory(self) -> None:
        adapter = ClaudeAdapter()
        findings = [
            RuleFinding(
                rule_id="F-001",
                title="t",
                severity=Severity.MEDIUM,
                additional_context="the tool failed, try another approach",
            )
        ]
        output = adapter.render_output(
            "PostToolUseFailure",
            findings,
            decision=None,
            context="the tool failed, try another approach",
            updated_input={},
        )
        assert output == {"systemMessage": "the tool failed, try another approach"}

    def test_posttool_use_failure_no_context_returns_none(self) -> None:
        adapter = ClaudeAdapter()
        findings = [
            RuleFinding(
                rule_id="F-002",
                title="t",
                severity=Severity.HIGH,
                decision="block",
                message="m",
            )
        ]
        # PostToolUseFailure ignores decision; only context produces output
        assert (
            adapter.render_output(
                "PostToolUseFailure",
                findings,
                decision="block",
                context=None,
                updated_input={},
            )
            is None
        )

    def test_stop_context_only_no_decision(self) -> None:
        """Stop with context but no blocking decision → systemMessage."""
        adapter = ClaudeAdapter()
        findings = [
            RuleFinding(
                rule_id="CTX-002",
                title="t",
                severity=Severity.LOW,
                additional_context="don't forget to commit",
            )
        ]
        output = adapter.render_output(
            "Stop",
            findings,
            decision=None,
            context="don't forget to commit",
            updated_input={},
        )
        assert output == {"systemMessage": "don't forget to commit"}

    def test_stop_block_with_context(self) -> None:
        """When Stop has both block + context, context appends to reason."""
        adapter = ClaudeAdapter()
        findings = [
            RuleFinding(
                rule_id="STOP-001",
                title="t",
                severity=Severity.HIGH,
                decision="block",
                message="unfinished tests",
                additional_context="also check lint",
            )
        ]
        output = adapter.render_output(
            "Stop",
            findings,
            decision="block",
            context="also check lint",
            updated_input={},
        )
        rendered = require_rendered(output)
        assert rendered["decision"] == "block", "Stop block must set decision=block"
        reason = support.required_string(rendered, "reason")
        assert "STOP-001" in reason, "rule id must appear in reason"
        assert "also check lint" in reason, "context must be appended to reason"

    def test_teammate_idle_context_only(self) -> None:
        adapter = ClaudeAdapter()
        findings = [
            RuleFinding(
                rule_id="CTX",
                title="t",
                severity=Severity.LOW,
                additional_context="work available in queue",
            )
        ]
        output = adapter.render_output(
            "TeammateIdle",
            findings,
            decision=None,
            context="work available in queue",
            updated_input={},
        )
        assert output == {"systemMessage": "work available in queue"}

    def test_unknown_event_returns_none(self) -> None:
        """Events not handled by any branch fall through to None."""
        adapter = ClaudeAdapter()
        findings = [
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
                "CompletelyFakeEvent",
                findings,
                decision="block",
                context=None,
                updated_input={},
            )
            is None
        )

    @pytest.mark.parametrize(
        "event",
        [
            "PreToolUse",
            "PermissionRequest",
            "PostToolUse",
            "Stop",
            "SessionStart",
            "UserPromptSubmit",
            "TaskCompleted",
            "TeammateIdle",
            "PostToolUseFailure",
            "ConfigChange",
            "SubagentStop",
        ],
    )
    def test_empty_findings_returns_none_for_all_events(self, event: str) -> None:
        """No findings → None for every event type."""
        adapter = ClaudeAdapter()
        assert (
            adapter.render_output(
                event,
                [],
                decision=None,
                context=None,
                updated_input={},
            )
            is None
        ), f"Empty findings must return None for event {event!r}"
