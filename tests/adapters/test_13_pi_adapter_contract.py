from __future__ import annotations

from slopgate.adapters.pi import PiAdapter
from slopgate.constants import POST_TOOL_USE, PRE_TOOL_USE
from tests.test_adapters import RuleFinding, Severity, require_rendered, support


def test_pi_normalizes_tool_call_payload() -> None:
    payload = PiAdapter().normalize_payload(
        {
            "hook_event_name": "tool_call",
            "tool_name": "bash",
            "tool_input": {"command": "pwd"},
        }
    )
    assert payload["hook_event_name"] == PRE_TOOL_USE
    assert payload["tool_name"] == "Bash"


def test_pi_pretool_deny_returns_block_result() -> None:
    output = PiAdapter().render_output(
        PRE_TOOL_USE,
        [
            RuleFinding(
                rule_id="PI-001",
                title="Pi block",
                severity=Severity.HIGH,
                decision="deny",
                message="blocked by policy",
            )
        ],
        decision="deny",
        context=None,
        updated_input={},
    )
    rendered = require_rendered(output)
    assert rendered["block"] is True
    assert "PI-001" in support.required_string(rendered, "reason")


def test_pi_pretool_allow_returns_updated_input() -> None:
    output = PiAdapter().render_output(
        PRE_TOOL_USE,
        [
            RuleFinding(
                rule_id="PI-MUTATE",
                title="Pi mutate",
                severity=Severity.LOW,
                decision="allow",
                message="normalized command",
            )
        ],
        decision="allow",
        context=None,
        updated_input={"command": "echo safe"},
    )
    assert output == {"updated_input": {"command": "echo safe"}}


def test_pi_context_only_returns_context() -> None:
    output = PiAdapter().render_output(
        "SessionStart",
        [
            RuleFinding(
                rule_id="PI-CONTEXT",
                title="Pi context",
                severity=Severity.LOW,
                additional_context="remember local rules",
            )
        ],
        decision=None,
        context="remember local rules",
        updated_input={},
    )
    assert output == {"context": "remember local rules"}


def test_pi_posttool_block_is_advisory_context_only() -> None:
    output = PiAdapter().render_output(
        POST_TOOL_USE,
        [
            RuleFinding(
                rule_id="PI-POST",
                title="Pi post tool",
                severity=Severity.HIGH,
                decision="block",
                message="post tool finding",
                additional_context="inspect the result",
            )
        ],
        decision="block",
        context="inspect the result",
        updated_input={},
    )
    assert output == {"context": "inspect the result"}
