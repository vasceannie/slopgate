from __future__ import annotations

from tests.test_adapters import (
    OpenCodeAdapter,
    PlatformAdapter,
    RuleFinding,
    Severity,
    pytest,
    require_rendered,
    test_support,
)

class TestOpenCodeAdapterRenderPostTool:
    """render_output for PostToolUse, Stop, SessionStart, and unknown events."""

    def test_posttool_block(self) -> None:
        adapter = OpenCodeAdapter()
        findings = [
            RuleFinding(
                rule_id="Q-001",
                title="t",
                severity=Severity.MEDIUM,
                decision="block",
                message="quality issue",
            )
        ]
        output = adapter.render_output(
            "PostToolUse",
            findings,
            decision="block",
            context=None,
            updated_input={},
        )
        assert output is not None, "PostToolUse block should produce output"
        assert output["action"] == "block", "PostToolUse block should map to block"
        assert "Q-001" in test_support.required_string(output, "reason"), (
            "rule id should appear in reason"
        )

    def test_posttool_with_context_and_decision(self) -> None:
        """PostToolUse block + context → both in output."""
        adapter = OpenCodeAdapter()
        findings = [
            RuleFinding(
                rule_id="Q-001",
                title="t",
                severity=Severity.MEDIUM,
                decision="block",
                message="quality issue",
                additional_context="consider adding tests",
            ),
        ]
        output = adapter.render_output(
            "PostToolUse",
            findings,
            decision="block",
            context="consider adding tests",
            updated_input={},
        )
        rendered = require_rendered(output)
        assert rendered["action"] == "block", "PostToolUse block should map to block"
        assert rendered["context"] == "consider adding tests", "context not included"
        assert "Q-001" in test_support.required_string(rendered, "reason"), (
            "rule id should appear in reason"
        )

    def test_posttool_context_only(self) -> None:
        """PostToolUse with only context, no block decision."""
        adapter = OpenCodeAdapter()
        findings = [
            RuleFinding(
                rule_id="CTX-001",
                title="t",
                severity=Severity.LOW,
                additional_context="check test coverage",
            ),
        ]
        output = adapter.render_output(
            "PostToolUse",
            findings,
            decision=None,
            context="check test coverage",
            updated_input={},
        )
        assert output == {"action": "context", "context": "check test coverage"}, (
            "context-only PostToolUse should return context action dict"
        )

    def test_stop_continue(self) -> None:
        adapter = OpenCodeAdapter()
        findings = [
            RuleFinding(
                rule_id="STOP-001",
                title="t",
                severity=Severity.HIGH,
                decision="block",
                message="run tests",
            )
        ]
        output = adapter.render_output(
            "Stop",
            findings,
            decision="block",
            context=None,
            updated_input={},
        )
        assert output is not None, "Stop with block should produce output"
        assert output["action"] == "continue", "Stop block should map to continue"
        assert "STOP-001" in test_support.required_string(output, "reason"), (
            "rule id should appear in reason"
        )

    def test_stop_context_only(self) -> None:
        """Stop with context but no block → context action."""
        adapter = OpenCodeAdapter()
        findings = [
            RuleFinding(
                rule_id="CTX",
                title="t",
                severity=Severity.LOW,
                additional_context="remember to commit",
            ),
        ]
        output = adapter.render_output(
            "Stop",
            findings,
            decision=None,
            context="remember to commit",
            updated_input={},
        )
        assert output == {"action": "context", "context": "remember to commit"}, (
            "Stop context-only should return context action dict"
        )

    def test_session_start_context(self) -> None:
        adapter = OpenCodeAdapter()
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
        assert output is not None, "SessionStart with context should produce output"
        assert output["action"] == "context", "SessionStart should use context action"

    def test_unknown_event_returns_none(self) -> None:
        adapter = OpenCodeAdapter()
        findings = [
            RuleFinding(
                rule_id="X",
                title="t",
                severity=Severity.HIGH,
                decision="block",
                message="m",
            ),
        ]
        assert (
            adapter.render_output(
                "TaskCompleted",
                findings,
                decision="block",
                context=None,
                updated_input={},
            )
            is None
        ), "unknown event should return None"

class TestBaseAdapterHelpers:
    """Test the static helper methods on PlatformAdapter."""

    @staticmethod
    def _mixed_decision_findings() -> list[RuleFinding]:
        return [
            RuleFinding(
                rule_id="A",
                title="t",
                severity=Severity.HIGH,
                decision="deny",
                message="a",
            ),
            RuleFinding(
                rule_id="B",
                title="t",
                severity=Severity.LOW,
                decision="allow",
                message="b",
            ),
            RuleFinding(
                rule_id="C",
                title="t",
                severity=Severity.MEDIUM,
                decision="deny",
                message="c",
            ),
            RuleFinding(
                rule_id="D",
                title="t",
                severity=Severity.LOW,
                decision=None,
                message="d",
            ),
        ]

    def test_join_messages_formats_rule_id_and_severity(self) -> None:
        findings = [
            RuleFinding(
                rule_id="GIT-001",
                title="t",
                severity=Severity.HIGH,
                message="hook bypass detected",
            ),
            RuleFinding(
                rule_id="SYS-002",
                title="t",
                severity=Severity.CRITICAL,
                message="system path violation",
            ),
        ]
        text = PlatformAdapter.join_messages(findings)
        assert "[GIT-001 | HIGH]" in text, "GIT-001 header not in output"
        assert "[SYS-002 | CRITICAL]" in text, "SYS-002 header not in output"
        assert "hook bypass detected" in text, "GIT-001 message not in output"
        assert "system path violation" in text, "SYS-002 message not in output"

    def test_join_messages_skips_none_messages(self) -> None:
        findings = [
            RuleFinding(rule_id="A", title="t", severity=Severity.LOW, message=None),
            RuleFinding(
                rule_id="B", title="t", severity=Severity.LOW, message="visible"
            ),
        ]
        text = PlatformAdapter.join_messages(findings)
        assert "visible" in text, "message 'visible' should appear in output"
        assert "A" not in text, "rule A has no message so should be omitted"

    def test_join_messages_empty_list(self) -> None:
        assert PlatformAdapter.join_messages([]) == ""

    @pytest.mark.parametrize(
        "decision, expected_ids",
        [
            pytest.param("deny", ["A", "C"], id="deny-findings"),
            pytest.param("allow", ["B"], id="allow-findings"),
            pytest.param(None, ["D"], id="none-findings"),
            pytest.param("block", [], id="empty-block-findings"),
        ],
    )
    def test_decision_findings_filters_correctly(
        self, decision: str | None, expected_ids: list[str]
    ) -> None:
        findings = PlatformAdapter.decision_findings(
            self._mixed_decision_findings(), decision
        )
        assert [f.rule_id for f in findings] == expected_ids, (
            f"{decision!r} filter returned wrong findings"
        )
