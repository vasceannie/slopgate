from __future__ import annotations

from hypothesis import given, strategies
import pytest

from slopgate.adapters.base import PlatformAdapter, RenderRequest
from slopgate.adapters.omp import OmpAdapter, render_post_tool
from slopgate.adapters.pi import PiAdapter
from slopgate.constants import POST_TOOL_USE
from slopgate.models import RuleFinding, Severity

_POST_TOOL_FAILURE = "PostToolUseFailure"
_REPAIR_MESSAGE = "post tool finding"
_REPAIR_CONTEXT = "inspect the result"
_BLOCKING_FINDING = RuleFinding(
    rule_id="POST-PIPELINE",
    title="Post tool pipeline",
    severity=Severity.HIGH,
    decision="block",
    message=_REPAIR_MESSAGE,
    additional_context=_REPAIR_CONTEXT,
)
_ADAPTERS = [
    pytest.param(OmpAdapter(), id="omp"),
    pytest.param(PiAdapter(), id="pi"),
]
_EVENTS = [
    pytest.param(POST_TOOL_USE, id="success"),
    pytest.param(_POST_TOOL_FAILURE, id="failure"),
]


def _render(adapter: PlatformAdapter, event_name: str) -> dict[str, object]:
    rendered = adapter.render_output(
        event_name,
        [_BLOCKING_FINDING],
        decision="block",
        context=_REPAIR_CONTEXT,
        updated_input={},
    )
    assert rendered is not None, "a blocking post-tool finding must render output"
    return rendered


@pytest.mark.parametrize("adapter", _ADAPTERS)
@pytest.mark.parametrize("event_name", _EVENTS)
def test_host_adapters_surface_post_tool_reason_without_a_veto(
    adapter: PlatformAdapter, event_name: str
) -> None:
    rendered = _render(adapter, event_name)

    assert _REPAIR_MESSAGE in str(rendered["reason"]), (
        "the blocking finding must reach the bridge as top-level reason text"
    )
    assert "block" not in rendered, (
        "post-tool findings are advisory and cannot request an execution veto"
    )


_BLOCKING_DECISIONS = frozenset({"block", "deny", "ask"})
_decisions = strategies.sampled_from(["block", "deny", "ask", "warn"])


def _request_for(context: str, message: str, decision: str) -> RenderRequest:
    finding = RuleFinding(
        rule_id="POST-PROPERTY",
        title="Post tool property",
        severity=Severity.HIGH,
        decision=decision,
        message=message,
    )
    return RenderRequest(
        event_name=POST_TOOL_USE,
        findings=[finding],
        context=context,
        updated_input={},
        decision=decision,
    )


@given(
    context=strategies.text(min_size=1),
    message=strategies.text(min_size=1),
    decision=_decisions,
)
def test_render_post_tool_details_mirror_top_level_reason(
    context: str, message: str, decision: str
) -> None:
    output = render_post_tool(OmpAdapter(), _request_for(context, message, decision))

    assert output["tool_result_patch"] == {
        "details": {
            "slopgate": {
                "decision": decision,
                "context": context,
                "reason": output.get("reason"),
            }
        }
    }, "structured details must mirror the top-level reason for every decision"


@given(
    context=strategies.text(min_size=1),
    message=strategies.text(min_size=1),
    decision=_decisions,
)
def test_render_post_tool_reason_only_for_blocking_decisions(
    context: str, message: str, decision: str
) -> None:
    output = render_post_tool(OmpAdapter(), _request_for(context, message, decision))

    assert output["context"] == context, "context must always reach the bridge"
    assert ("reason" in output) == (decision in _BLOCKING_DECISIONS), (
        "only blocking decisions carry a reason; advisory decisions stay context-only"
    )
