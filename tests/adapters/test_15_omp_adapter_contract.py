from __future__ import annotations

from typing import Final

import pytest

from slopgate.adapters import ADAPTERS, get_adapter
from slopgate.adapters.omp import OmpAdapter, USER_PROMPT_SUBMIT, _OMP_EVENT_ALIASES
from slopgate.constants import (
    POST_TOOL_USE,
    PRE_TOOL_USE,
    SESSION_START,
    STOP,
)
from slopgate.models import RuleFinding, Severity

_OMP_EVENT_CASES: Final = (
    pytest.param("tool_call", PRE_TOOL_USE, id="tool-call"),
    pytest.param("tool_result", POST_TOOL_USE, id="tool-result"),
    pytest.param("session_start", SESSION_START, id="session-start"),
    pytest.param("input", USER_PROMPT_SUBMIT, id="input"),
    pytest.param("session_stop", STOP, id="session-stop"),
    pytest.param("turn_end", "TurnEnd", id="turn-end"),
    pytest.param("agent_end", "agent_end", id="agent-end-telemetry"),
    pytest.param("tool_execution_start", "tool_execution_start", id="tool-start"),
    pytest.param("tool_execution_update", "tool_execution_update", id="tool-update"),
    pytest.param("tool_execution_end", "tool_execution_end", id="tool-end"),
    pytest.param("before_agent_start", "before_agent_start", id="local-injection"),
    pytest.param("user_bash", PRE_TOOL_USE, id="user-bash"),
    pytest.param("user_python", PRE_TOOL_USE, id="user-python"),
)


def test_omp_adapter_is_registered() -> None:
    assert "omp" in ADAPTERS and get_adapter("omp").name == "omp", (
        "omp must be registered and resolve to OmpAdapter"
    )


def test_unknown_platform_error_lists_omp() -> None:
    with pytest.raises(ValueError, match=r"Valid options: .*omp"):
        _ = get_adapter("vim")


def test_omp_alias_inventory_matches_the_pinned_event_union() -> None:
    assert len(_OMP_EVENT_ALIASES) == 45, "OMP aliases must cover all 45 pinned events"
    assert {"user_bash", "user_python"} <= _OMP_EVENT_ALIASES.keys(), (
        "OMP aliases must include both direct execution events"
    )


@pytest.mark.parametrize(
    ("omp_event", "canonical_event"),
    _OMP_EVENT_CASES,
)
def test_omp_normalizes_pinned_event_map(
    omp_event: str,
    canonical_event: str,
) -> None:
    payload = OmpAdapter().normalize_payload({"hook_event_name": omp_event})
    assert payload["hook_event_name"] == canonical_event, (
        f"{omp_event} must normalize to {canonical_event}"
    )


@pytest.mark.parametrize(
    ("is_error", "canonical_event"),
    [
        pytest.param(False, POST_TOOL_USE, id="success"),
        pytest.param(True, "PostToolUseFailure", id="failure"),
    ],
)
def test_omp_tool_result_uses_is_error_to_discriminate_failures(
    is_error: bool,
    canonical_event: str,
) -> None:
    payload = OmpAdapter().normalize_payload(
        {
            "hook_event_name": "tool_result",
            "isError": is_error,
            "tool_name": "bash",
            "tool_result": "done",
        }
    )
    assert payload["hook_event_name"] == canonical_event, (
        "tool_result isError must select the canonical post-tool event"
    )


@pytest.mark.parametrize(
    ("omp_event", "raw_field", "raw_value", "tool_name"),
    [
        pytest.param("user_bash", "command", "pwd", "Bash", id="bash"),
        pytest.param("user_python", "code", "print(1)", "Python", id="python"),
    ],
)
def test_omp_normalizes_direct_user_execution(
    omp_event: str,
    raw_field: str,
    raw_value: str,
    tool_name: str,
) -> None:
    payload = OmpAdapter().normalize_payload(
        {
            "hook_event_name": omp_event,
            raw_field: raw_value,
            "session_id": "omp-session",
            "cwd": ".",
        }
    )
    assert payload["hook_event_name"] == PRE_TOOL_USE, (
        "direct user execution must cross the pre-tool gate"
    )
    assert payload["tool_name"] == tool_name, "direct execution needs a canonical tool"
    assert payload["tool_input"] == {raw_field: raw_value}, (
        "direct execution input must preserve the raw command or code"
    )


def test_omp_pretool_deny_returns_block_reason() -> None:
    finding = RuleFinding(
        rule_id="OMP-BLOCK",
        title="OMP block",
        severity=Severity.HIGH,
        decision="deny",
        message="blocked by policy",
    )
    output = OmpAdapter().render_output(
        PRE_TOOL_USE,
        [finding],
        decision="deny",
        context=None,
        updated_input={},
    )
    assert output is not None and output.get("block") is True, (
        "pre-tool deny must block OMP execution"
    )
    assert "OMP-BLOCK" in str(output.get("reason")), "deny must identify the rule"


def test_omp_pretool_allow_returns_platform_neutral_updated_input() -> None:
    finding = RuleFinding(
        rule_id="OMP-REWRITE",
        title="OMP rewrite",
        severity=Severity.LOW,
        decision="allow",
        message="rewrite command",
    )
    output = OmpAdapter().render_output(
        PRE_TOOL_USE,
        [finding],
        decision="allow",
        context=None,
        updated_input={"command": "echo safe"},
    )
    assert output == {"updated_input": {"command": "echo safe"}}, (
        "OMP bridge must receive the platform-neutral updated_input contract"
    )


def test_omp_prompt_deny_returns_handled_reason_without_action() -> None:
    finding = RuleFinding(
        rule_id="OMP-PROMPT",
        title="OMP prompt",
        severity=Severity.HIGH,
        decision="block",
        message="prompt blocked",
    )
    output = OmpAdapter().render_output(
        USER_PROMPT_SUBMIT,
        [finding],
        decision="block",
        context=None,
        updated_input={},
    )
    assert output is not None and output.get("handled") is True, (
        "OMP prompt denial must short-circuit input"
    )
    assert "OMP-PROMPT" in str(output.get("reason")) and "action" not in output, (
        "OMP prompt denial must identify the rule without Pi action strings"
    )


def test_omp_stop_block_returns_continuation_guidance() -> None:
    finding = RuleFinding(
        rule_id="OMP-STOP",
        title="OMP stop",
        severity=Severity.HIGH,
        decision="block",
        message="finish the repair",
        additional_context="repair before stopping",
    )
    output = OmpAdapter().render_output(
        STOP,
        [finding],
        decision="block",
        context="repair before stopping",
        updated_input={},
    )
    assert output == {
        "continue": True,
        "additionalContext": "repair before stopping",
    }, "blocking session_stop must request one OMP continuation"


def test_omp_stop_advisory_returns_context_only() -> None:
    finding = RuleFinding(
        rule_id="OMP-ADVISORY",
        title="OMP advisory",
        severity=Severity.LOW,
        decision="warn",
        message="quality reminder",
        additional_context="run project checks",
    )
    output = OmpAdapter().render_output(
        STOP,
        [finding],
        decision="warn",
        context="run project checks",
        updated_input={},
    )
    assert output == {"context": "run project checks"}, (
        "non-blocking session_stop findings must remain advisory"
    )


@pytest.mark.parametrize(
    "event_name",
    [
        pytest.param(POST_TOOL_USE, id="success"),
        pytest.param("PostToolUseFailure", id="failure"),
    ],
)
def test_omp_posttool_events_return_advisory_patch(event_name: str) -> None:
    finding = RuleFinding(
        rule_id="OMP-POST",
        title="OMP post tool",
        severity=Severity.HIGH,
        decision="block",
        message="inspect result",
        additional_context="inspect the result",
    )
    output = OmpAdapter().render_output(
        event_name,
        [finding],
        decision="block",
        context="inspect the result",
        updated_input={},
    )
    assert output == {
        "context": "inspect the result",
        "tool_result_patch": {
            "details": {
                "slopgate": {
                    "decision": "block",
                    "context": "inspect the result",
                    "reason": None,
                }
            }
        },
    }, "both successful and failed tool results must use advisory patches"


def test_omp_session_start_returns_context() -> None:
    finding = RuleFinding(
        rule_id="OMP-CONTEXT",
        title="OMP context",
        severity=Severity.LOW,
        decision="context",
        message="load repository rules",
        additional_context="load repository rules",
    )
    output = OmpAdapter().render_output(
        SESSION_START,
        [finding],
        decision="context",
        context="load repository rules",
        updated_input={},
    )
    assert output == {"context": "load repository rules"}, (
        "session_start context must be available for bridge caching"
    )
