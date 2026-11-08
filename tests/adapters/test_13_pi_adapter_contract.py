from __future__ import annotations

from typing import Final

import pytest

from slopgate._types import ObjectDict
from slopgate.adapters.pi import PiAdapter
from slopgate.constants import POST_TOOL_USE, PRE_TOOL_USE
from tests.test_adapters import RuleFinding, Severity, require_rendered, support

_PI_FAILURE_CASES: Final = (
    pytest.param({"isError": True}, id="top-level-is-error"),
    pytest.param({"details": {"exitCode": 2}}, id="top-level-exit-code"),
    pytest.param({"details": {"exit_code": 2}}, id="top-level-exit-code-alias"),
)


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


def test_pi_normalizes_user_bash_payload() -> None:
    payload = PiAdapter().normalize_payload(
        {
            "hook_event_name": "user_bash",
            "tool_name": "bash",
            "tool_input": {"command": "pwd"},
        }
    )
    assert payload["hook_event_name"] == PRE_TOOL_USE
    assert payload["tool_name"] == "Bash"


def test_pi_normalizes_raw_user_bash_command() -> None:
    payload = PiAdapter().normalize_payload(
        {
            "hook_event_name": "user_bash",
            "command": "python -c 'print(1)'",
            "excludeFromContext": True,
        }
    )
    assert payload["hook_event_name"] == PRE_TOOL_USE, (
        "Pi user bash events must normalize to PreToolUse"
    )
    assert payload["tool_name"] == "Bash", "Pi user bash must use canonical Bash"
    assert payload["tool_input"] == {
        "command": "python -c 'print(1)'",
        "exclude_from_context": True,
    }, "Pi user bash must preserve command context fields"


def test_pi_normalizes_transcript_style_tool_arguments() -> None:
    payload = PiAdapter().normalize_payload(
        {
            "hook_event_name": "tool_call",
            "name": "ctx_execute",
            "arguments": {"language": "python", "code": "from typing import Any"},
        }
    )
    assert payload["hook_event_name"] == PRE_TOOL_USE, (
        "Pi transcript tool calls must normalize to PreToolUse"
    )
    assert payload["tool_name"] == "ctx_execute", (
        "Pi transcript tool calls must preserve unknown tool names"
    )
    assert payload["tool_input"] == {
        "language": "python",
        "code": "from typing import Any",
    }, "Pi transcript arguments must normalize to tool_input"


@pytest.mark.parametrize("failure_fields", _PI_FAILURE_CASES)
def test_pi_failed_tool_results_map_to_post_tool_use_failure(
    failure_fields: ObjectDict,
) -> None:
    payload = PiAdapter().normalize_payload(
        {
            "hook_event_name": "tool_result",
            "tool_name": "bash",
            "tool_result": {"stdout": "failed"},
            **failure_fields,
        }
    )
    assert payload["hook_event_name"] == "PostToolUseFailure", (
        "Pi failure signals must select the canonical post-tool failure event"
    )


def test_pi_zero_exit_maps_to_post_tool_use() -> None:
    payload = PiAdapter().normalize_payload(
        {
            "hook_event_name": "tool_result",
            "tool_result": {"stdout": "done"},
            "details": {"exitCode": 0},
        }
    )
    assert payload["hook_event_name"] == POST_TOOL_USE, (
        "Pi exit code zero must remain a successful post-tool event"
    )


@pytest.mark.parametrize(
    "canonical_event",
    [
        pytest.param(POST_TOOL_USE, id="success"),
        pytest.param("PostToolUseFailure", id="failure"),
    ],
)
def test_pi_premapped_post_tool_events_pass_through(canonical_event: str) -> None:
    payload = PiAdapter().normalize_payload(
        {
            "hook_event_name": canonical_event,
            "isError": True,
            "details": {"exitCode": 2},
        }
    )
    assert payload["hook_event_name"] == canonical_event, (
        "Pi canonical post-tool events must pass through unchanged"
    )


@pytest.mark.parametrize(
    ("raw_event", "canonical_event"),
    [
        pytest.param("session_start", "SessionStart", id="startup"),
        pytest.param("before_agent_start", "before_agent_start", id="run-preparation"),
        pytest.param(
            "tool_execution_end", "tool_execution_end", id="execution-notification"
        ),
    ],
)
def test_pi_session_start_is_only_native_startup(
    raw_event: str, canonical_event: str
) -> None:
    payload = PiAdapter().normalize_payload({"hook_event_name": raw_event})
    assert payload["hook_event_name"] == canonical_event, (
        "Pi startup is the native session_start event; run preparation and "
        "execution notifications must not alias to canonical lifecycle events"
    )


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


def test_pi_posttool_block_reports_reason_and_context_for_native_result() -> None:
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
    rendered = require_rendered(output)
    reason = support.required_string(rendered, "reason")
    assert "post tool finding" in reason
    assert rendered["context"] == "inspect the result"
    assert rendered["tool_result_patch"] == {
        "details": {
            "slopgate": {
                "decision": "block",
                "context": "inspect the result",
                "reason": reason,
            }
        }
    }
    assert "block" not in rendered, "post-tool findings cannot roll back execution"


def test_pi_post_tool_failure_renders_like_success() -> None:
    output = PiAdapter().render_output(
        "PostToolUseFailure",
        [
            RuleFinding(
                rule_id="PI-POST-FAIL",
                title="Pi failed post tool",
                severity=Severity.HIGH,
                decision="block",
                message="failure finding",
            )
        ],
        decision="block",
        context=None,
        updated_input={},
    )
    rendered = require_rendered(output)
    assert "failure finding" in support.required_string(rendered, "reason")
    assert "tool_result_patch" in rendered
