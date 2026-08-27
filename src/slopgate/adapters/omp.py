"""Oh My Pi adapter for OMP-native lifecycle events."""

from __future__ import annotations

from typing import Final

from typing_extensions import override

from slopgate._types import (
    ObjectDict,
    ObjectMapping,
    is_object_dict,
    object_dict,
    string_value,
)
from slopgate.adapters._payload_fields import (
    PI_FAMILY_TOOL_MAP,
    canonical_event_name,
    canonical_payload_with_event,
    merge_standard_session_fields,
    sync_tool_result_fields,
)
from slopgate.adapters._session_identity import SESSION_IDENTITY_TELEMETRY
from slopgate.adapters.base import PlatformAdapter, RenderRequest, render_request_from_call
from slopgate.constants import (
    ASK,
    BLOCK,
    DECISION_KEY,
    DENY,
    METADATA_COMMAND,
    METADATA_SLOPGATE,
    METADATA_TOOL_NAME,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    SESSION_START,
    STOP,
)


USER_PROMPT_SUBMIT: Final[str] = "UserPromptSubmit"

_OMP_EVENT_ALIASES: dict[str, str] = {
    "after_provider_response": "after_provider_response",
    "agent_end": "agent_end",
    "agent_start": "agent_start",
    "auto_compaction_end": "auto_compaction_end",
    "auto_compaction_start": "auto_compaction_start",
    "auto_retry_end": "auto_retry_end",
    "auto_retry_start": "auto_retry_start",
    "before_agent_start": "before_agent_start",
    "before_provider_request": "before_provider_request",
    "context": "context",
    "credential_disabled": "credential_disabled",
    "goal_updated": "goal_updated",
    "input": USER_PROMPT_SUBMIT,
    "mcp_notification": "mcp_notification",
    "message_end": "message_end",
    "message_start": "message_start",
    "message_update": "message_update",
    "resources_discover": "resources_discover",
    "retry_fallback_applied": "retry_fallback_applied",
    "retry_fallback_succeeded": "retry_fallback_succeeded",
    "session.compacting": "session.compacting",
    "session_before_branch": "session_before_branch",
    "session_before_compact": "session_before_compact",
    "session_before_switch": "session_before_switch",
    "session_before_tree": "session_before_tree",
    "session_branch": "session_branch",
    "session_compact": "session_compact",
    "session_shutdown": "session_shutdown",
    "session_start": "SessionStart",
    "session_stop": "Stop",
    "session_switch": "session_switch",
    "session_tree": "session_tree",
    "todo_reminder": "todo_reminder",
    "tool_approval_requested": "tool_approval_requested",
    "tool_approval_resolved": "tool_approval_resolved",
    "tool_call": PRE_TOOL_USE,
    "tool_execution_end": "tool_execution_end",
    "tool_execution_start": "tool_execution_start",
    "tool_execution_update": "tool_execution_update",
    "tool_result": "PostToolUse",
    "ttsr_triggered": "ttsr_triggered",
    "turn_end": "TurnEnd",
    "turn_start": "turn_start",
    "user_bash": PRE_TOOL_USE,
    "user_python": PRE_TOOL_USE,
}

_OMP_CANONICAL_EVENTS = set(_OMP_EVENT_ALIASES.values()) | {"PostToolUseFailure"}


def _raw_event_name(raw: ObjectMapping) -> str:
    SESSION_IDENTITY_TELEMETRY.record_metric("omp.event.raw_name")
    event = string_value(raw.get("hook_event_name")) or string_value(
        raw.get("hookEventName")
    )
    if event is None:
        return ""
    return event.lower().replace("-", "")


def _canonical_event_name(raw: ObjectMapping) -> str:
    SESSION_IDENTITY_TELEMETRY.record_metric("omp.event.canonical_name")
    event_name = canonical_event_name(raw, _OMP_CANONICAL_EVENTS, _OMP_EVENT_ALIASES)
    if _raw_event_name(raw) == "tool_result" and raw.get("isError") is True:
        return "PostToolUseFailure"
    return event_name


def _canonical_tool_name(raw: ObjectMapping) -> str:
    SESSION_IDENTITY_TELEMETRY.record_metric("omp.tool.canonical_name")
    tool = (
        string_value(raw.get(METADATA_TOOL_NAME))
        or string_value(raw.get("toolName"))
        or string_value(raw.get("tool"))
        or string_value(raw.get("name"))
    )
    if not tool:
        return ""
    normalized = tool.lower().strip()
    return PI_FAMILY_TOOL_MAP.get(normalized, tool)


def _sync_tool_input(raw: ObjectMapping, canonical: ObjectDict) -> None:
    SESSION_IDENTITY_TELEMETRY.record_metric("omp.tool.sync_input")
    if is_object_dict(canonical.get("tool_input")):
        return
    for key in ("input", "args", "arguments"):
        value = raw.get(key)
        if is_object_dict(value):
            canonical["tool_input"] = object_dict(value)
            return


def _sync_user_bash_command(raw: ObjectMapping, canonical: ObjectDict) -> None:
    SESSION_IDENTITY_TELEMETRY.record_metric("omp.user_bash.sync_command")
    if _raw_event_name(raw) != "user_bash":
        return
    command = string_value(raw.get(METADATA_COMMAND))
    if not command:
        return
    canonical.setdefault(METADATA_TOOL_NAME, "Bash")
    tool_input = object_dict(canonical.get("tool_input"))
    tool_input.setdefault(METADATA_COMMAND, command)
    if raw.get("excludeFromContext") is True:
        tool_input.setdefault("exclude_from_context", True)
    canonical["tool_input"] = tool_input


def _sync_user_python_code(raw: ObjectMapping, canonical: ObjectDict) -> None:
    SESSION_IDENTITY_TELEMETRY.record_metric("omp.user_python.sync_code")
    if _raw_event_name(raw) != "user_python":
        return
    code = string_value(raw.get("code"))
    if not code:
        return
    tool_input = object_dict(canonical.get("tool_input"))
    if "code" not in tool_input:
        tool_input["code"] = code
    canonical["tool_input"] = tool_input
    canonical.setdefault(METADATA_TOOL_NAME, "Python")


def _render_pre_tool_use(
    adapter: PlatformAdapter,
    request: RenderRequest,
) -> ObjectDict | None:
    SESSION_IDENTITY_TELEMETRY.record_metric("omp.render.pre_tool_use")
    if request.decision in {DENY, BLOCK, ASK}:
        return {
            BLOCK: True,
            "reason": adapter.join_messages(
                adapter.decision_findings(request.findings, request.decision)
            ),
        }
    if request.decision == "allow" and request.updated_input:
        return {"updated_input": request.updated_input}
    if request.context:
        return {"context": request.context}
    return None


def _render_prompt_submit(
    adapter: PlatformAdapter,
    request: RenderRequest,
) -> ObjectDict | None:
    blocking_findings = adapter.decision_findings(request.findings, request.decision)
    SESSION_IDENTITY_TELEMETRY.record_metric("omp.render.prompt_submit")
    if request.decision in {DENY, BLOCK, ASK}:
        return {
            "handled": True,
            "reason": adapter.join_messages(blocking_findings),
        }
    if request.context:
        return {"context": request.context}
    return None


def _render_stop(
    adapter: PlatformAdapter,
    request: RenderRequest,
) -> ObjectDict | None:
    SESSION_IDENTITY_TELEMETRY.record_metric("omp.render.stop")
    if request.decision in {DENY, BLOCK, ASK}:
        blocking_findings = adapter.decision_findings(
            request.findings, request.decision
        )
        reason = adapter.join_messages(blocking_findings)
        return {
            "continue": True,
            "additionalContext": request.context or reason,
        }
    if request.context:
        return {"context": request.context}
    return None


def _render_post_tool(
    adapter: PlatformAdapter,
    request: RenderRequest,
) -> ObjectDict:
    SESSION_IDENTITY_TELEMETRY.record_metric("omp.render.post_tool", adapter.name)
    output: ObjectDict = {}
    if request.context:
        output["context"] = request.context
    slopgate_details: ObjectDict = {
        DECISION_KEY: request.decision,
        "context": request.context,
        "reason": None,
    }
    patch_details: ObjectDict = {METADATA_SLOPGATE: slopgate_details}
    output["tool_result_patch"] = {"details": patch_details}
    return output


def _render_context(
    adapter: PlatformAdapter,
    request: RenderRequest,
) -> ObjectDict | None:
    SESSION_IDENTITY_TELEMETRY.record_metric("omp.render.context", adapter.name)
    return {"context": request.context} if request.context else None


class OmpAdapter(PlatformAdapter):
    """Translate OMP lifecycle events into Slopgate's canonical format."""

    name: str = "omp"

    @override
    def normalize_payload(self, raw: ObjectMapping) -> ObjectDict:
        SESSION_IDENTITY_TELEMETRY.record_metric("omp.normalize_payload")
        canonical = canonical_payload_with_event(raw, _canonical_event_name(raw))
        merge_standard_session_fields(raw, canonical)
        _sync_tool_input(raw, canonical)
        _sync_user_python_code(raw, canonical)
        _sync_user_bash_command(raw, canonical)
        tool_name = _canonical_tool_name(raw)
        if tool_name:
            canonical[METADATA_TOOL_NAME] = tool_name
        sync_tool_result_fields(canonical)
        return canonical

    @override
    def render_output(
        self,
        *args: object,
        **kwargs: object,
    ) -> ObjectDict | None:
        request = render_request_from_call(args, kwargs)
        SESSION_IDENTITY_TELEMETRY.record_metric("omp.render_output")
        if not request.findings:
            return None
        if request.event_name == PRE_TOOL_USE:
            return _render_pre_tool_use(self, request)
        if request.event_name == USER_PROMPT_SUBMIT:
            return _render_prompt_submit(self, request)
        if request.event_name == STOP:
            return _render_stop(self, request)
        if request.event_name in {POST_TOOL_USE, "PostToolUseFailure"}:
            return _render_post_tool(self, request)
        if request.event_name == SESSION_START:
            return _render_context(self, request)
        return None
