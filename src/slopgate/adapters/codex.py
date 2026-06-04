"""Codex CLI adapter."""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import override

from slopgate._types import (
    ObjectDict,
    ObjectMapping,
    is_object_dict,
    object_dict,
    string_value,
)
from slopgate.adapters._payload_fields import (
    merge_standard_session_fields,
    sync_tool_result_fields,
)
from slopgate.adapters.base import (
    PlatformAdapter,
    hook_specific_context_output,
    render_request_from_call,
    render_permission_request_output,
)
from slopgate.constants import BLOCK, DENY, PERMISSION_REQUEST, POST_TOOL_USE, PRE_TOOL_USE
from slopgate.models import RuleFinding, Severity

CODEX_EVENTS = {
    "SessionStart",
    PRE_TOOL_USE,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    "UserPromptSubmit",
    "Stop",
}

_CODEX_EVENT_ALIASES: dict[str, str] = {
    "sessionstart": "SessionStart",
    "pretooluse": PRE_TOOL_USE,
    "permissionrequest": PERMISSION_REQUEST,
    "posttooluse": POST_TOOL_USE,
    "userpromptsubmit": "UserPromptSubmit",
    "stop": "Stop",
}


def _canonical_codex_event(raw: ObjectMapping) -> str:
    event = string_value(raw.get("hook_event_name")) or string_value(raw.get("hookEventName"))
    if not event:
        return ""
    if event in CODEX_EVENTS:
        return event
    return _CODEX_EVENT_ALIASES.get(event.lower().replace("-", ""), event)


@dataclass(frozen=True, slots=True)
class _CodexRenderRequest:
    event_name: str
    findings: list[RuleFinding]
    context: str | None
    updated_input: ObjectDict
    decision: str | None


def _codex_decision_reason(
    adapter: PlatformAdapter, request: _CodexRenderRequest
) -> str:
    return adapter.join_messages(
        adapter.decision_findings(request.findings, request.decision)
    )


def _apply_codex_block_decision(
    adapter: PlatformAdapter,
    payload: ObjectDict,
    request: _CodexRenderRequest,
) -> None:
    if request.decision not in {BLOCK, DENY, "ask"}:
        return
    payload["decision"] = BLOCK
    payload["reason"] = _codex_decision_reason(adapter, request)


def _add_codex_pretool_context_and_rewrite(
    specific: ObjectDict, request: _CodexRenderRequest
) -> None:
    updates: ObjectDict = {}
    if request.updated_input:
        updates["updatedInput"] = request.updated_input
    if request.context:
        updates["additionalContext"] = request.context
    specific.update(updates)


def _render_codex_pre_tool_use(
    adapter: PlatformAdapter, request: _CodexRenderRequest
) -> ObjectDict | None:
    specific: ObjectDict = {"hookEventName": PRE_TOOL_USE}
    if request.decision in {DENY, BLOCK, "ask"}:
        specific["permissionDecision"] = DENY
        specific["permissionDecisionReason"] = _codex_decision_reason(
            adapter, request
        )
    elif request.decision == "allow":
        specific["permissionDecision"] = "allow"
    if request.decision == "allow":
        _add_codex_pretool_context_and_rewrite(specific, request)
    elif request.context:
        specific["additionalContext"] = request.context
    response: ObjectDict = {"hookSpecificOutput": specific}
    return response if len(specific) > 1 else None


def _render_codex_permission_request(
    adapter: PlatformAdapter, request: _CodexRenderRequest
) -> ObjectDict | None:
    return render_permission_request_output(
        PERMISSION_REQUEST,
        request.decision,
        _codex_decision_reason(adapter, request),
    )


def _critical_codex_posttool_blocks(
    request: _CodexRenderRequest,
) -> list[RuleFinding]:
    return [
        finding
        for finding in request.findings
        if finding.decision == BLOCK and finding.severity >= Severity.CRITICAL
    ]


def _render_critical_codex_posttool(
    adapter: PlatformAdapter,
    request: _CodexRenderRequest,
    critical_blocks: list[RuleFinding],
) -> ObjectDict:
    critical_response: ObjectDict = {
        "continue": False,
        "stopReason": adapter.join_messages(critical_blocks),
    }
    if request.context:
        critical_response.update(hook_specific_context_output(POST_TOOL_USE, request.context))
    return critical_response


def _render_codex_post_tool_use(
    adapter: PlatformAdapter, request: _CodexRenderRequest
) -> ObjectDict | None:
    critical_blocks = _critical_codex_posttool_blocks(request)
    if critical_blocks:
        return _render_critical_codex_posttool(adapter, request, critical_blocks)

    payload: ObjectDict = {}
    _apply_codex_block_decision(adapter, payload, request)
    if request.context:
        payload.update(hook_specific_context_output(POST_TOOL_USE, request.context))
    return payload or None


def _render_codex_prompt_submit(
    adapter: PlatformAdapter, request: _CodexRenderRequest
) -> ObjectDict | None:
    payload: ObjectDict = {}
    _apply_codex_block_decision(adapter, payload, request)
    if request.context:
        payload.update(hook_specific_context_output("UserPromptSubmit", request.context))
    return payload or None


def _render_codex_stop(
    adapter: PlatformAdapter, request: _CodexRenderRequest
) -> ObjectDict | None:
    payload: ObjectDict = {}
    _apply_codex_block_decision(adapter, payload, request)
    if request.context and not payload.get("decision"):
        payload["systemMessage"] = request.context
    elif request.context:
        existing = string_value(payload.get("reason"))
        payload["reason"] = (
            (existing + "\n\n" + request.context).strip()
            if existing
            else request.context
        )
    return payload or None


class CodexAdapter(PlatformAdapter):
    name: str = "codex"

    @override
    def normalize_payload(self, raw: ObjectMapping) -> ObjectDict:
        canonical = object_dict(raw) if is_object_dict(raw) else object_dict(raw)
        event_name = _canonical_codex_event(raw)
        if event_name:
            canonical["hook_event_name"] = event_name
        merge_standard_session_fields(raw, canonical)
        sync_tool_result_fields(canonical)
        return canonical

    @override
    def render_output(
        self,
        *args: object,
        **kwargs: object,
    ) -> ObjectDict | None:
        render_request = render_request_from_call(args, kwargs)
        if not render_request.findings:
            return None
        if render_request.event_name not in CODEX_EVENTS:
            return None

        request = _CodexRenderRequest(
            event_name=render_request.event_name,
            findings=render_request.findings,
            context=render_request.context,
            updated_input=render_request.updated_input,
            decision=render_request.decision,
        )

        if request.event_name == PRE_TOOL_USE:
            return _render_codex_pre_tool_use(self, request)

        if request.event_name == PERMISSION_REQUEST:
            return _render_codex_permission_request(self, request)

        if request.event_name == POST_TOOL_USE:
            return _render_codex_post_tool_use(self, request)

        if request.event_name == "SessionStart":
            if request.context:
                return hook_specific_context_output("SessionStart", request.context)
            return None

        if request.event_name == "UserPromptSubmit":
            return _render_codex_prompt_submit(self, request)

        if request.event_name == "Stop":
            return _render_codex_stop(self, request)

        return None
