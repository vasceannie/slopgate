"""OpenCode adapter."""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import override

from slopgate._types import ObjectDict, ObjectMapping, object_dict, string_value
from slopgate.adapters._payload_fields import (
    merge_standard_session_fields,
    sync_tool_result_fields,
)
from slopgate.adapters.base import PlatformAdapter, render_request_from_call
from slopgate.adapters.opencode_identity import opencode_session_identity
from slopgate.models import RuleFinding

from slopgate.constants import (
    ASK,
    BLOCK,
    DENY,
    METADATA_TOOL_NAME,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    SESSION_START,
    STOP,
    TOOL_BASH,
)

OPENCODE_EVENT_MAP: dict[str, str] = {
    "command.executed": "CommandExecuted",
    "file.edited": POST_TOOL_USE,
    "permission.replied": "PermissionReplied",
    "shell.env": "ShellEnv",
    "session.compacted": "PostCompact",
    "tool.execute.before": PRE_TOOL_USE,
    "tool.execute.after": POST_TOOL_USE,
    "session.created": SESSION_START,
    "session.idle": STOP,
    "session.error": "SessionError",
    "session.status": "SessionStatus",
    "permission.asked": PERMISSION_REQUEST,
}

OPENCODE_TOOL_ALIAS_MAP: dict[str, str] = {
    TOOL_BASH: "Bash",
    "edit": "Edit",
    "glob": "Glob",
    "grep": "Grep",
    "multiedit": "MultiEdit",
    "notebookedit": "NotebookEdit",
    "read": "Read",
    "todowrite": "TodoWrite",
    "webfetch": "WebFetch",
    "websearch": "WebSearch",
    "write": "Write",
}

OPENCODE_MUTATION_EVENTS = frozenset({"file.edited"})


class _AdapterTelemetry:
    def record_metric(self, *values: object) -> None:
        return None


_ADAPTER_TELEMETRY = _AdapterTelemetry()


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
        _ADAPTER_TELEMETRY.record_metric("opencode.normalize_payload")
        canonical = object_dict(raw)
        oc_event = string_value(raw.get("hook_event_name")) or ""
        canonical_event = OPENCODE_EVENT_MAP.get(oc_event, oc_event)
        canonical["hook_event_name"] = canonical_event
        if oc_event:
            canonical["opencode_hook_event"] = oc_event

        tool_name = string_value(raw.get(METADATA_TOOL_NAME)) or ""
        if not tool_name and oc_event in OPENCODE_MUTATION_EVENTS:
            tool_name = "Write"
        if tool_name:
            lowered = tool_name.strip().lower().replace("-", "_")
            canonical[METADATA_TOOL_NAME] = OPENCODE_TOOL_ALIAS_MAP.get(
                lowered, tool_name
            )

        merge_standard_session_fields(raw, canonical, cwd_extra_keys=("directory",))
        opencode_session_identity(raw).apply_to(canonical)
        sync_tool_result_fields(canonical)
        return canonical

    def _block_output(
        self, request: _OpenCodeRenderRequest, action: str = BLOCK
    ) -> ObjectDict:
        _ADAPTER_TELEMETRY.record_metric("opencode.render.block")
        reason = self.join_messages(
            self.decision_findings(request.findings, request.decision)
        )
        return {"action": action, "reason": reason}

    @staticmethod
    def _context_output(context: str) -> ObjectDict:
        _ADAPTER_TELEMETRY.record_metric("opencode.render.context")
        return {"action": "context", "context": context}

    def _render_pre_tool_use(
        self, request: _OpenCodeRenderRequest
    ) -> ObjectDict | None:
        _ADAPTER_TELEMETRY.record_metric("opencode.render.pre_tool_use")
        if request.decision in {DENY, BLOCK, ASK}:
            result = self._block_output(request)
            if request.context:
                result["context"] = request.context
            return result
        if request.decision == "allow" and request.updated_input:
            result: ObjectDict = {
                "action": "allow",
                "updated_args": request.updated_input,
            }
            if request.context:
                result["context"] = request.context
            return result
        if request.context:
            return self._context_output(request.context)
        return None

    def _render_permission_request(
        self, request: _OpenCodeRenderRequest
    ) -> ObjectDict | None:
        _ADAPTER_TELEMETRY.record_metric("opencode.render.permission_request")
        if request.decision in {DENY, BLOCK, ASK}:
            return self._block_output(request)
        if request.decision == "allow" and request.updated_input:
            return {"action": "allow", "updated_args": request.updated_input}
        return None

    def _render_post_tool_use(
        self, request: _OpenCodeRenderRequest
    ) -> ObjectDict | None:
        _ADAPTER_TELEMETRY.record_metric("opencode.render.post_tool_use")
        payload: ObjectDict = {}
        if request.decision in {BLOCK, DENY}:
            payload.update(self._block_output(request))
        if request.context:
            if "action" not in payload:
                payload["action"] = "context"
            payload["context"] = request.context
        return payload or None

    def _render_session_start(
        self, request: _OpenCodeRenderRequest
    ) -> ObjectDict | None:
        _ADAPTER_TELEMETRY.record_metric("opencode.render.session_start")
        if request.context:
            return self._context_output(request.context)
        return None

    def _render_stop(self, request: _OpenCodeRenderRequest) -> ObjectDict | None:
        _ADAPTER_TELEMETRY.record_metric("opencode.render.stop")
        if request.decision in {BLOCK, DENY, ASK}:
            reason = self.join_messages(
                self.decision_findings(request.findings, request.decision)
            )
            return {
                "action": "continue",
                "reason": reason,
            }
        if request.context:
            return self._context_output(request.context)
        return None

    @override
    def render_output(
        self,
        *args: object,
        **kwargs: object,
    ) -> ObjectDict | None:
        _ADAPTER_TELEMETRY.record_metric("opencode.render_output")
        render_request = render_request_from_call(args, kwargs)
        if not render_request.findings:
            return None

        request = _OpenCodeRenderRequest(
            event_name=render_request.event_name,
            findings=render_request.findings,
            context=render_request.context,
            updated_input=render_request.updated_input,
            decision=render_request.decision,
        )

        if request.event_name == PRE_TOOL_USE:
            return self._render_pre_tool_use(request)

        if request.event_name == PERMISSION_REQUEST:
            return self._render_permission_request(request)

        if request.event_name == POST_TOOL_USE:
            return self._render_post_tool_use(request)

        if request.event_name == SESSION_START:
            return self._render_session_start(request)

        if request.event_name == STOP:
            return self._render_stop(request)

        return None
