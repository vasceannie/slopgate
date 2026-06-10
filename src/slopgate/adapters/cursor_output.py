"""Cursor hook stdout rendering (separate from payload normalization)."""

from __future__ import annotations

from dataclasses import dataclass

from slopgate._types import ObjectDict
from slopgate.adapters.base import PlatformAdapter, render_request_from_call
from slopgate.constants import (
    BLOCK,
    DENY,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
)
from slopgate.models import RuleFinding

_PERMISSION_EVENTS = frozenset(
    {
        PRE_TOOL_USE,
        PERMISSION_REQUEST,
        "SubagentStart",
    }
)
_POST_TOOL_EVENTS = frozenset({POST_TOOL_USE})
_FOLLOWUP_EVENTS = frozenset({"Stop", "SubagentStop"})


@dataclass(frozen=True, slots=True)
class CursorRenderRequest:
    event_name: str
    findings: list[RuleFinding]
    context: str | None
    updated_input: ObjectDict
    decision: str | None


def _decision_text(adapter: PlatformAdapter, request: CursorRenderRequest) -> str:
    findings = adapter.decision_findings(request.findings, request.decision)
    if not findings:
        findings = request.findings
    return adapter.join_messages(findings)


def _append_context(message: str, context: str | None) -> str:
    if not context:
        return message
    if not message:
        return context
    return f"{message}\n\n{context}"


def _deny_permission_output(
    adapter: PlatformAdapter, request: CursorRenderRequest
) -> ObjectDict:
    reason = _decision_text(adapter, request)
    payload: ObjectDict = {
        "permission": "deny",
        "user_message": reason,
    }
    if request.event_name != "SubagentStart":
        payload["agent_message"] = _append_context(reason, request.context)
    return payload


def _ask_permission_output(
    adapter: PlatformAdapter, request: CursorRenderRequest
) -> ObjectDict:
    reason = _decision_text(adapter, request)
    return {
        "permission": "ask",
        "user_message": reason,
        "agent_message": _append_context(reason, request.context),
    }


def _allow_permission_output(request: CursorRenderRequest) -> ObjectDict:
    payload: ObjectDict = {"permission": "allow"}
    if request.updated_input:
        payload["updated_input"] = request.updated_input
    if request.context:
        payload["agent_message"] = request.context
    return payload


def _permission_gate_output(
    adapter: PlatformAdapter, request: CursorRenderRequest
) -> ObjectDict | None:
    if request.decision in {DENY, BLOCK}:
        return _deny_permission_output(adapter, request)
    if request.decision == "ask":
        return _ask_permission_output(adapter, request)
    if request.decision == "allow" or request.updated_input:
        return _allow_permission_output(request)
    if request.context:
        return {"permission": "allow", "agent_message": request.context}
    return None


def _post_tool_output(
    adapter: PlatformAdapter, request: CursorRenderRequest
) -> ObjectDict | None:
    reason = _decision_text(adapter, request)
    message = _append_context(reason, request.context) if reason else request.context
    if not message:
        return None
    return {"additional_context": message}


def _prompt_submit_output(
    adapter: PlatformAdapter, request: CursorRenderRequest
) -> ObjectDict | None:
    if request.decision in {DENY, BLOCK, "ask"}:
        return {
            "continue": False,
            "user_message": _decision_text(adapter, request),
        }
    if request.context:
        return {"continue": True, "user_message": request.context}
    return None


def _contextual_message(adapter: PlatformAdapter, request: CursorRenderRequest) -> str:
    return _append_context(_decision_text(adapter, request), request.context)


def _output_for_message(message: str, field: str) -> ObjectDict | None:
    if not message:
        return None
    return {field: message}


def _render_without_findings(request: CursorRenderRequest) -> ObjectDict | None:
    if request.event_name in _PERMISSION_EVENTS:
        return _allow_permission_output(request)
    if request.event_name == "UserPromptSubmit":
        return {"continue": True}
    return None


def _render_with_findings(
    adapter: PlatformAdapter,
    request: CursorRenderRequest,
) -> ObjectDict | None:
    if request.event_name in _PERMISSION_EVENTS:
        return _permission_gate_output(adapter, request)
    if request.event_name in _POST_TOOL_EVENTS:
        return _post_tool_output(adapter, request)
    if request.event_name == "UserPromptSubmit":
        return _prompt_submit_output(adapter, request)
    if request.event_name in _FOLLOWUP_EVENTS:
        if request.decision in {DENY, BLOCK, "ask"} or request.context:
            message = _contextual_message(adapter, request)
            return _output_for_message(message, "followup_message")
        return None
    if request.event_name == "PreCompact":
        return _output_for_message(
            _contextual_message(adapter, request), "user_message"
        )
    if request.event_name == "SessionStart" and request.context:
        return _output_for_message(
            _contextual_message(adapter, request), "additional_context"
        )
    if request.context:
        return {"agent_message": request.context}
    return None


def render_cursor_output(
    adapter: PlatformAdapter,
    request: CursorRenderRequest,
) -> ObjectDict | None:
    """Map engine findings to Cursor-native hook JSON."""
    if not request.findings:
        return _render_without_findings(request)
    return _render_with_findings(adapter, request)


def cursor_render_request_from_call(
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> CursorRenderRequest:
    """Build a :class:`CursorRenderRequest` from ``render_output`` call arguments."""
    render_request = render_request_from_call(args, kwargs)
    return CursorRenderRequest(
        event_name=render_request.event_name,
        findings=render_request.findings,
        context=render_request.context,
        updated_input=render_request.updated_input,
        decision=render_request.decision,
    )
