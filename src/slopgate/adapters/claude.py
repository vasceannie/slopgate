"""Claude Code adapter — the original/default platform."""

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
from slopgate.adapters._payload_fields import merge_standard_session_fields
from slopgate.adapters.base import (
    PlatformAdapter,
    hook_specific_context_output,
    render_request_from_call,
    render_permission_request_output,
)
from slopgate.constants import (
    BLOCK,
    DENY,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
)
from slopgate.models import RuleFinding

_CLAUDE_EVENT_ALIASES: dict[str, str] = {
    "pretooluse": PRE_TOOL_USE,
    "posttooluse": POST_TOOL_USE,
    "posttoolusefailure": "PostToolUseFailure",
    "permissionrequest": PERMISSION_REQUEST,
    "userpromptsubmit": "UserPromptSubmit",
    "sessionstart": "SessionStart",
    "sessionend": "SessionEnd",
    "subagentstart": "SubagentStart",
    "subagentstop": "SubagentStop",
}


def _canonical_event_name(raw: ObjectMapping) -> str:
    event = string_value(raw.get("hook_event_name")) or string_value(
        raw.get("hookEventName")
    )
    if not event:
        return ""
    if event in _CLAUDE_EVENT_ALIASES.values():
        return event
    return _CLAUDE_EVENT_ALIASES.get(event.lower().replace("-", ""), event)


@dataclass(frozen=True, slots=True)
class _ClaudeRenderRequest:
    event_name: str
    findings: list[RuleFinding]
    context: str | None
    updated_input: ObjectDict
    decision: str | None


class ClaudeAdapter(PlatformAdapter):
    name: str = "claude"

    @override
    def normalize_payload(self, raw: ObjectMapping) -> ObjectDict:
        canonical = object_dict(raw) if is_object_dict(raw) else object_dict(raw)
        event_name = _canonical_event_name(raw)
        if event_name:
            canonical["hook_event_name"] = event_name
        merge_standard_session_fields(raw, canonical)
        return canonical

    def _decision_reason(self, request: _ClaudeRenderRequest) -> str:
        return self.join_messages(
            self.decision_findings(request.findings, request.decision)
        )

    def _render_hook_specific_permission(
        self, request: _ClaudeRenderRequest, hook_event_name: str
    ) -> ObjectDict | None:
        specific: ObjectDict = {"hookEventName": hook_event_name}
        if request.decision in {DENY, "ask", "allow"}:
            specific["permissionDecision"] = request.decision
            specific["permissionDecisionReason"] = self._decision_reason(request)
        elif request.decision == BLOCK:
            specific["permissionDecision"] = DENY
            specific["permissionDecisionReason"] = self._decision_reason(request)
        if request.updated_input:
            specific["updatedInput"] = request.updated_input
        if request.context:
            specific["additionalContext"] = request.context
        response: ObjectDict = {"hookSpecificOutput": specific}
        return response if len(specific) > 1 else None

    def _render_pre_tool_use(self, request: _ClaudeRenderRequest) -> ObjectDict | None:
        return self._render_hook_specific_permission(request, PRE_TOOL_USE)

    def _render_permission_request(
        self, request: _ClaudeRenderRequest
    ) -> ObjectDict | None:
        return render_permission_request_output(
            PERMISSION_REQUEST,
            request.decision,
            self._decision_reason(request),
            request.updated_input,
        )

    def _render_prompt_or_posttool(
        self, request: _ClaudeRenderRequest
    ) -> ObjectDict | None:
        payload: ObjectDict = {}
        if request.decision in {BLOCK, DENY, "ask"}:
            payload["decision"] = BLOCK
            payload["reason"] = self._decision_reason(request)
        if request.context:
            payload.update(
                hook_specific_context_output(request.event_name, request.context)
            )
        return payload or None

    def _render_stop_like(self, request: _ClaudeRenderRequest) -> ObjectDict | None:
        payload: ObjectDict = {}
        if request.decision in {BLOCK, DENY, "ask"}:
            payload["decision"] = BLOCK
            payload["reason"] = self._decision_reason(request)
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

    def _render_task_or_idle(self, request: _ClaudeRenderRequest) -> ObjectDict | None:
        if request.decision in {BLOCK, DENY, "ask"}:
            return None
        if request.context:
            return {"systemMessage": request.context}
        return None

    @override
    def render_output(
        self,
        *args: object,
        **kwargs: object,
    ) -> ObjectDict | None:
        render_request = render_request_from_call(args, kwargs)
        if not render_request.findings:
            return None

        request = _ClaudeRenderRequest(
            event_name=render_request.event_name,
            findings=render_request.findings,
            context=render_request.context,
            updated_input=render_request.updated_input,
            decision=render_request.decision,
        )

        if request.event_name in {PRE_TOOL_USE, "SubagentStart"}:
            return self._render_hook_specific_permission(request, request.event_name)

        if request.event_name == PERMISSION_REQUEST:
            return self._render_permission_request(request)

        if request.event_name == "SessionStart":
            if request.context:
                return hook_specific_context_output("SessionStart", request.context)
            return None

        if request.event_name in {"UserPromptSubmit", POST_TOOL_USE}:
            return self._render_prompt_or_posttool(request)

        if request.event_name in {"Stop", "SubagentStop", "ConfigChange"}:
            return self._render_stop_like(request)

        if request.event_name == "PostToolUseFailure":
            if request.context:
                return {"systemMessage": request.context}
            return None

        if request.event_name in {"TaskCompleted", "TeammateIdle"}:
            return self._render_task_or_idle(request)

        return None
