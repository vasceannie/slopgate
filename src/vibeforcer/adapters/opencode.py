"""OpenCode adapter."""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import override

from vibeforcer._types import ObjectDict, ObjectMapping, object_dict, string_value
from vibeforcer.adapters.base import PlatformAdapter
from vibeforcer.models import RuleFinding

from vibeforcer.constants import BLOCK, DENY, PERMISSION_REQUEST, POST_TOOL_USE, PRE_TOOL_USE
OPENCODE_EVENT_MAP: dict[str, str] = {
    "tool.execute.before": PRE_TOOL_USE,
    "tool.execute.after": POST_TOOL_USE,
    "session.created": "SessionStart",
    "session.idle": "Stop",
    "permission.asked": PERMISSION_REQUEST,
}


@dataclass(frozen=True, slots=True)
class _OpenCodeRenderRequest:
    event_name: str
    findings: list[RuleFinding]
    context: str | None
    updated_input: ObjectDict
    decision: str | None


class OpenCodeAdapter(PlatformAdapter):
    name: str = "opencode"

    @override
    def normalize_payload(self, raw: ObjectMapping) -> ObjectDict:
        canonical = object_dict(raw)
        oc_event = string_value(raw.get("hook_event_name")) or ""
        canonical_event = OPENCODE_EVENT_MAP.get(oc_event, oc_event)
        canonical["hook_event_name"] = canonical_event

        tool_name = string_value(raw.get("tool_name")) or ""
        if tool_name and tool_name[0].islower():
            canonical["tool_name"] = tool_name.capitalize()

        if "tool_response" in canonical and "tool_result" not in canonical:
            canonical["tool_result"] = canonical["tool_response"]
        elif "tool_result" in canonical and "tool_response" not in canonical:
            canonical["tool_response"] = canonical["tool_result"]
        return canonical

    def _decision_reason(self, request: _OpenCodeRenderRequest) -> str:
        return self.join_messages(
            self.decision_findings(request.findings, request.decision)
        )

    def _block_output(self, request: _OpenCodeRenderRequest, action: str = BLOCK) -> ObjectDict:
        return {"action": action, "reason": self._decision_reason(request)}

    @staticmethod
    def _context_output(context: str) -> ObjectDict:
        return {"action": "context", "context": context}

    def _render_pre_tool_use(
        self, request: _OpenCodeRenderRequest
    ) -> ObjectDict | None:
        if request.decision in {DENY, BLOCK, "ask"}:
            result = self._block_output(request)
            if request.context:
                result["context"] = request.context
            return result
        if request.decision == "allow" and request.updated_input:
            result: ObjectDict = {"action": "allow", "updated_args": request.updated_input}
            if request.context:
                result["context"] = request.context
            return result
        if request.context:
            return self._context_output(request.context)
        return None

    def _render_permission_request(
        self, request: _OpenCodeRenderRequest
    ) -> ObjectDict | None:
        if request.decision in {DENY, BLOCK, "ask"}:
            return self._block_output(request)
        if request.decision == "allow" and request.updated_input:
            return {"action": "allow", "updated_args": request.updated_input}
        return None

    def _render_post_tool_use(
        self, request: _OpenCodeRenderRequest
    ) -> ObjectDict | None:
        payload: ObjectDict = {}
        if request.decision in {BLOCK, DENY}:
            payload.update(self._block_output(request))
        if request.context:
            payload["context"] = request.context
        return payload or None

    def _render_session_start(
        self, request: _OpenCodeRenderRequest
    ) -> ObjectDict | None:
        if request.context:
            return self._context_output(request.context)
        return None

    def _render_stop(self, request: _OpenCodeRenderRequest) -> ObjectDict | None:
        if request.decision in {BLOCK, DENY}:
            return self._block_output(request, action="continue")
        if request.context:
            return self._context_output(request.context)
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

        request = _OpenCodeRenderRequest(
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

        if event_name == POST_TOOL_USE:
            return self._render_post_tool_use(request)

        if event_name == "SessionStart":
            return self._render_session_start(request)

        if event_name == "Stop":
            return self._render_stop(request)

        return None
