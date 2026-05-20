"""Claude Code adapter — the original/default platform."""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import override

from vibeforcer._types import (
    ObjectDict,
    ObjectMapping,
    is_object_dict,
    object_dict,
    string_value,
)
from vibeforcer.adapters.base import (
    PlatformAdapter,
    hook_specific_context_output,
    render_permission_request_output,
)
from vibeforcer.constants import BLOCK, DENY, PERMISSION_REQUEST, POST_TOOL_USE, PRE_TOOL_USE
from vibeforcer.models import RuleFinding


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
        if is_object_dict(raw):
            return raw
        return object_dict(raw)

    def _decision_reason(self, request: _ClaudeRenderRequest) -> str:
        return self.join_messages(
            self.decision_findings(request.findings, request.decision)
        )

    def _render_pre_tool_use(self, request: _ClaudeRenderRequest) -> ObjectDict | None:
        specific: ObjectDict = {"hookEventName": PRE_TOOL_USE}
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

    def _render_permission_request(
        self, request: _ClaudeRenderRequest
    ) -> ObjectDict | None:
        return render_permission_request_output(
            PERMISSION_REQUEST,
            request.decision,
            self._decision_reason(request),
            request.updated_input,
        )

    def _render_prompt_or_posttool(self, request: _ClaudeRenderRequest) -> ObjectDict | None:
        payload: ObjectDict = {}
        if request.decision in {BLOCK, DENY, "ask"}:
            payload["decision"] = BLOCK
            payload["reason"] = self._decision_reason(request)
        if request.context:
            payload.update(hook_specific_context_output(request.event_name, request.context))
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
        if request.decision in {BLOCK, DENY}:
            return {
                "continue": False,
                "stopReason": self._decision_reason(request),
            }
        if request.context:
            return {"systemMessage": request.context}
        return None

    @override
    def render_output(
        self,
        event_name: str,
        findings: list[RuleFinding],
        *,
        context: str | None = None,
        updated_input: ObjectDict | None = None,
        decision: str | None = None,
    ) -> ObjectDict | None:
        if not findings:
            return None

        request = _ClaudeRenderRequest(
            event_name=event_name,
            findings=findings,
            context=context,
            updated_input=updated_input or {},
            decision=decision,
        )

        if event_name == PRE_TOOL_USE:
            return self._render_pre_tool_use(request)

        if event_name == PERMISSION_REQUEST:
            return self._render_permission_request(request)

        if event_name == "SessionStart":
            if context:
                return hook_specific_context_output("SessionStart", context)
            return None

        if event_name in {"UserPromptSubmit", POST_TOOL_USE}:
            return self._render_prompt_or_posttool(request)

        if event_name in {"Stop", "SubagentStop", "ConfigChange"}:
            return self._render_stop_like(request)

        if event_name == "PostToolUseFailure":
            if context:
                return {"systemMessage": context}
            return None

        if event_name in {"TaskCompleted", "TeammateIdle"}:
            return self._render_task_or_idle(request)

        return None
