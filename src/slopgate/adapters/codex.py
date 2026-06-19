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
    canonical_event_name,
    merge_standard_session_fields,
    sync_tool_result_fields,
)
from slopgate.adapters.base import (
    PlatformAdapter,
    hook_specific_context_output,
    render_request_from_call,
    render_permission_request_output,
)
from slopgate.adapters.codex_identity import codex_session_identity
from slopgate.constants import (
    ASK,
    BLOCK,
    DENY,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    SESSION_START,
    STOP,
)
from slopgate.models import RuleFinding, Severity

CODEX_EVENTS = {
    SESSION_START,
    "SubagentStart",
    PRE_TOOL_USE,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    "PreCompact",
    "PostCompact",
    "UserPromptSubmit",
    "SubagentStop",
    STOP,
}

_CODEX_EVENT_ALIASES: dict[str, str] = {
    "postcompact": "PostCompact",
    "precompact": "PreCompact",
    "sessionstart": SESSION_START,
    "subagentstart": "SubagentStart",
    "pretooluse": PRE_TOOL_USE,
    "permissionrequest": PERMISSION_REQUEST,
    "posttooluse": POST_TOOL_USE,
    "userpromptsubmit": "UserPromptSubmit",
    "subagentstop": "SubagentStop",
    "stop": STOP,
}
class _CodexTelemetry:
    def record_metric(self, *values: object) -> None:
        return None


_CODEX_TELEMETRY = _CodexTelemetry()


def _canonical_codex_event(raw: ObjectMapping) -> str:
    _CODEX_TELEMETRY.record_metric("codex.event.canonicalize")
    return canonical_event_name(raw, CODEX_EVENTS, _CODEX_EVENT_ALIASES)


@dataclass(frozen=True, slots=True)
class _CodexRenderRequest:
    event_name: str
    findings: list[RuleFinding]
    context: str | None
    updated_input: ObjectDict
    decision: str | None


def _apply_codex_block_decision(
    adapter: PlatformAdapter,
    payload: ObjectDict,
    request: _CodexRenderRequest,
) -> None:
    _CODEX_TELEMETRY.record_metric("codex.render.block_decision")
    if request.decision not in {BLOCK, DENY, ASK}:
        return
    payload["decision"] = BLOCK
    payload["reason"] = adapter.join_messages(
        adapter.decision_findings(request.findings, request.decision)
    )


def _codex_decision_payload(
    adapter: PlatformAdapter, request: _CodexRenderRequest
) -> ObjectDict:
    _CODEX_TELEMETRY.record_metric("codex.render.decision_payload")
    payload: ObjectDict = {}
    _apply_codex_block_decision(adapter, payload, request)
    return payload


def _add_codex_pretool_context_and_rewrite(
    specific: ObjectDict, request: _CodexRenderRequest
) -> None:
    _CODEX_TELEMETRY.record_metric("codex.render.pretool_context")
    updates: ObjectDict = {}
    if request.updated_input:
        updates["updatedInput"] = request.updated_input
    if request.context:
        updates["additionalContext"] = request.context
    specific.update(updates)


def _render_codex_pre_tool_use(
    adapter: PlatformAdapter, request: _CodexRenderRequest
) -> ObjectDict | None:
    _CODEX_TELEMETRY.record_metric("codex.render.pretool")
    specific: ObjectDict = {"hookEventName": PRE_TOOL_USE}
    if request.decision in {DENY, BLOCK, ASK}:
        specific["permissionDecision"] = DENY
        specific["permissionDecisionReason"] = adapter.join_messages(
            adapter.decision_findings(request.findings, request.decision)
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
    _CODEX_TELEMETRY.record_metric("codex.render.permission_request")
    decision_findings = adapter.decision_findings(request.findings, request.decision)
    reason = adapter.join_messages(decision_findings)
    return render_permission_request_output(
        PERMISSION_REQUEST,
        request.decision,
        reason,
    )


def _critical_codex_posttool_blocks(
    request: _CodexRenderRequest,
) -> list[RuleFinding]:
    _CODEX_TELEMETRY.record_metric("codex.render.critical_posttool_blocks")
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
    _CODEX_TELEMETRY.record_metric("codex.render.critical_posttool")
    critical_response: ObjectDict = {
        "continue": False,
        "stopReason": adapter.join_messages(critical_blocks),
    }
    if request.context:
        critical_response.update(
            hook_specific_context_output(POST_TOOL_USE, request.context)
        )
    return critical_response


def _render_codex_post_tool_use(
    adapter: PlatformAdapter, request: _CodexRenderRequest
) -> ObjectDict | None:
    _CODEX_TELEMETRY.record_metric("codex.render.posttool")
    critical_blocks = _critical_codex_posttool_blocks(request)
    if critical_blocks:
        return _render_critical_codex_posttool(adapter, request, critical_blocks)

    payload = _codex_decision_payload(adapter, request)
    if request.context:
        payload.update(hook_specific_context_output(POST_TOOL_USE, request.context))
    return payload or None


def _render_codex_prompt_submit(
    adapter: PlatformAdapter, request: _CodexRenderRequest
) -> ObjectDict | None:
    _CODEX_TELEMETRY.record_metric("codex.render.prompt_submit")
    payload = _codex_decision_payload(adapter, request)
    if request.context:
        payload.update(
            hook_specific_context_output("UserPromptSubmit", request.context)
        )
    return payload or None


def _render_codex_stop(
    adapter: PlatformAdapter, request: _CodexRenderRequest
) -> ObjectDict | None:
    _CODEX_TELEMETRY.record_metric("codex.render.stop")
    payload = _codex_decision_payload(adapter, request)
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


def _render_codex_lifecycle_context(request: _CodexRenderRequest) -> ObjectDict | None:
    _CODEX_TELEMETRY.record_metric("codex.render.lifecycle_context")
    if not request.context:
        return None
    return hook_specific_context_output(request.event_name, request.context)


class CodexAdapter(PlatformAdapter):
    name: str = "codex"

    @override
    def normalize_payload(self, raw: ObjectMapping) -> ObjectDict:
        _CODEX_TELEMETRY.record_metric("codex.normalize_payload")
        canonical = object_dict(raw) if is_object_dict(raw) else object_dict(raw)
        event_name = _canonical_codex_event(raw)
        if event_name:
            canonical["hook_event_name"] = event_name
        merge_standard_session_fields(raw, canonical)
        codex_session_identity(raw).apply_to(canonical)
        sync_tool_result_fields(canonical)
        return canonical

    @override
    def render_output(
        self,
        *args: object,
        **kwargs: object,
    ) -> ObjectDict | None:
        _CODEX_TELEMETRY.record_metric("codex.render_output")
        render_request = render_request_from_call(args, kwargs)
        if render_request.event_name not in CODEX_EVENTS:
            return None
        if not render_request.findings:
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

        if request.event_name in {
            "PostCompact",
            "PreCompact",
            SESSION_START,
            "SubagentStart",
            "SubagentStop",
        }:
            return _render_codex_lifecycle_context(request)

        if request.event_name == "UserPromptSubmit":
            return _render_codex_prompt_submit(self, request)

        if request.event_name == STOP:
            return _render_codex_stop(self, request)

        return None
