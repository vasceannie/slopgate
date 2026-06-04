"""Cursor adapter for native Cursor hooks.

Output shapes follow https://cursor.com/docs/agent/hooks — notably
``beforeSubmitPrompt`` uses ``continue``/``user_message``, ``postToolUse`` uses
``additional_context`` (no hard deny), and ``stop``/``subagentStop`` use
``followup_message``.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import override

from slopgate._types import ObjectDict, ObjectMapping, object_dict, string_value
from slopgate.adapters.base import PlatformAdapter, render_request_from_call
from slopgate.constants import BLOCK, DENY, PERMISSION_REQUEST, POST_TOOL_USE, PRE_TOOL_USE
from slopgate.models import RuleFinding

_CURSOR_EVENT_MAP: dict[str, str] = {
    "preToolUse": PRE_TOOL_USE,
    "postToolUse": POST_TOOL_USE,
    "postToolUseFailure": "PostToolUseFailure",
    "beforeShellExecution": PRE_TOOL_USE,
    "afterShellExecution": POST_TOOL_USE,
    "beforeMCPExecution": PRE_TOOL_USE,
    "afterMCPExecution": POST_TOOL_USE,
    "beforeReadFile": PRE_TOOL_USE,
    "beforeTabFileRead": PRE_TOOL_USE,
    "afterFileEdit": POST_TOOL_USE,
    "afterTabFileEdit": POST_TOOL_USE,
    "beforeSubmitPrompt": "UserPromptSubmit",
    "sessionStart": "SessionStart",
    "sessionEnd": "SessionEnd",
    "stop": "Stop",
    "subagentStart": "SubagentStart",
    "subagentStop": "SubagentStop",
    "preCompact": "PreCompact",
    "afterAgentResponse": "AfterAgentResponse",
    "afterAgentThought": "AfterAgentThought",
    "workspaceOpen": "WorkspaceOpen",
}

_CURSOR_TOOL_ALIAS_MAP: dict[str, str] = {
    "bash": "Bash",
    "shell": "Bash",
    "terminal": "Bash",
    "read": "Read",
    "read_file": "Read",
    "edit": "Edit",
    "write": "Write",
    "file_edit": "Write",
    "after_file_edit": "Write",
    "grep": "Grep",
    "glob": "Glob",
    "webfetch": "WebFetch",
    "websearch": "WebSearch",
}

_SHELL_EVENTS = frozenset({"beforeShellExecution", "afterShellExecution"})
_READ_EVENTS = frozenset({"beforeReadFile", "beforeTabFileRead"})
_FILE_EDIT_EVENTS = frozenset({"afterFileEdit", "afterTabFileEdit"})
_MCP_EVENTS = frozenset({"beforeMCPExecution", "afterMCPExecution"})
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
class _CursorRenderRequest:
    event_name: str
    findings: list[RuleFinding]
    context: str | None
    updated_input: ObjectDict
    decision: str | None


def _first_string(raw: ObjectMapping, *keys: str) -> str:
    for key in keys:
        value = string_value(raw.get(key))
        if value and value.strip():
            return value.strip()
    return ""


def _nested_tool_input(raw: ObjectMapping) -> ObjectDict:
    for key in ("tool_input", "toolInput", "tool_args", "args", "arguments", "input"):
        candidate = object_dict(raw.get(key))
        if candidate:
            return candidate
    tool = object_dict(raw.get("tool"))
    for key in ("input", "args", "arguments"):
        candidate = object_dict(tool.get(key))
        if candidate:
            return candidate
    return {}


def _tool_name_from_raw(raw: ObjectMapping, cursor_event: str) -> str:
    if cursor_event in _SHELL_EVENTS:
        return "Bash"
    if cursor_event in _READ_EVENTS:
        return "Read"
    if cursor_event in _FILE_EDIT_EVENTS:
        return "Write"

    raw_name = _first_string(raw, "tool_name", "toolName", "tool")
    if not raw_name:
        raw_name = _first_string(object_dict(raw.get("tool")), "name")
    lowered = raw_name.strip().lower().replace("-", "_")
    return _CURSOR_TOOL_ALIAS_MAP.get(lowered, raw_name)


def _shell_tool_input(raw: ObjectMapping, tool_input: ObjectDict) -> ObjectDict:
    command = _first_string(raw, "command", "cmd", "script") or _first_string(
        tool_input, "command", "cmd", "script"
    )
    if command:
        tool_input = dict(tool_input)
        tool_input.setdefault("command", command)
    return tool_input


def _file_tool_input(raw: ObjectMapping, tool_input: ObjectDict) -> ObjectDict:
    file_path = _first_string(
        raw,
        "file_path",
        "filePath",
        "path",
        "resolved_file_path",
        "original_file_path",
    ) or _first_string(
        tool_input,
        "file_path",
        "filePath",
        "path",
        "resolved_file_path",
        "original_file_path",
    )
    if file_path:
        tool_input = dict(tool_input)
        tool_input.setdefault("file_path", file_path)
    edits = raw.get("edits")
    if edits is not None and "edits" not in tool_input:
        tool_input = dict(tool_input)
        tool_input["edits"] = edits
    return tool_input


def _cursor_tool_input(raw: ObjectMapping, cursor_event: str) -> ObjectDict:
    tool_input = _nested_tool_input(raw)
    if cursor_event in _SHELL_EVENTS:
        return _shell_tool_input(raw, tool_input)
    if cursor_event in _READ_EVENTS or cursor_event in _FILE_EDIT_EVENTS:
        return _file_tool_input(raw, tool_input)
    if cursor_event in _MCP_EVENTS:
        return tool_input
    return tool_input


def _decision_text(adapter: PlatformAdapter, request: _CursorRenderRequest) -> str:
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


def _workspace_cwd(raw: ObjectMapping, canonical: ObjectDict) -> None:
    cwd = _first_string(raw, "cwd", "workspaceRoot", "workspace_root", "project_path")
    if cwd:
        canonical["cwd"] = cwd
        return
    roots = raw.get("workspace_roots")
    if isinstance(roots, list):
        for item in roots:
            root = string_value(item)
            if root and root.strip():
                canonical["cwd"] = root.strip()
                return


def _sync_tool_result_fields(canonical: ObjectDict, raw: ObjectMapping) -> None:
    tool_output = raw.get("tool_output")
    if tool_output is not None:
        if "tool_result" not in canonical:
            canonical["tool_result"] = tool_output
        if "tool_response" not in canonical:
            canonical["tool_response"] = tool_output
    if "tool_response" in canonical and "tool_result" not in canonical:
        canonical["tool_result"] = canonical["tool_response"]
    elif "tool_result" in canonical and "tool_response" not in canonical:
        canonical["tool_response"] = canonical["tool_result"]


class CursorAdapter(PlatformAdapter):
    name: str = "cursor"

    @override
    def normalize_payload(self, raw: ObjectMapping) -> ObjectDict:
        canonical = object_dict(raw)
        cursor_event = _first_string(raw, "hook_event_name", "hookEventName", "event_name", "event")
        canonical["hook_event_name"] = _CURSOR_EVENT_MAP.get(cursor_event, cursor_event)
        if cursor_event:
            canonical["cursor_hook_event"] = cursor_event

        session_id = _first_string(raw, "session_id", "sessionId", "conversation_id", "conversationId")
        if session_id:
            canonical["session_id"] = session_id

        _workspace_cwd(raw, canonical)

        tool_name = _tool_name_from_raw(raw, cursor_event)
        if tool_name:
            canonical["tool_name"] = tool_name
        tool_input = _cursor_tool_input(raw, cursor_event)
        if tool_input:
            canonical["tool_input"] = tool_input

        if cursor_event in _FILE_EDIT_EVENTS and "tool_response" not in canonical:
            canonical["tool_response"] = {"file_path": tool_input.get("file_path", "")}
        _sync_tool_result_fields(canonical, raw)

        prompt = _first_string(raw, "prompt", "user_prompt", "userPrompt")
        if prompt:
            canonical["prompt"] = prompt
        return canonical

    def _deny_permission_output(self, request: _CursorRenderRequest) -> ObjectDict:
        reason = _decision_text(self, request)
        payload: ObjectDict = {
            "permission": "deny",
            "user_message": reason,
        }
        if request.event_name != "SubagentStart":
            payload["agent_message"] = _append_context(reason, request.context)
        return payload

    def _ask_permission_output(self, request: _CursorRenderRequest) -> ObjectDict:
        reason = _decision_text(self, request)
        return {
            "permission": "ask",
            "user_message": reason,
            "agent_message": _append_context(reason, request.context),
        }

    def _allow_permission_output(self, request: _CursorRenderRequest) -> ObjectDict | None:
        payload: ObjectDict = {"permission": "allow"}
        if request.updated_input:
            payload["updated_input"] = request.updated_input
        if request.context:
            payload["agent_message"] = request.context
        return payload if len(payload) > 1 else None

    def _permission_gate_output(self, request: _CursorRenderRequest) -> ObjectDict | None:
        if request.decision in {DENY, BLOCK}:
            return self._deny_permission_output(request)
        if request.decision == "ask":
            return self._ask_permission_output(request)
        if request.decision == "allow" or request.updated_input:
            return self._allow_permission_output(request)
        if request.context:
            return {"permission": "allow", "agent_message": request.context}
        return None

    def _post_tool_output(self, request: _CursorRenderRequest) -> ObjectDict | None:
        reason = _decision_text(self, request)
        message = _append_context(reason, request.context) if reason else request.context
        if not message:
            return None
        return {"additional_context": message}

    def _prompt_submit_output(self, request: _CursorRenderRequest) -> ObjectDict | None:
        if request.decision in {DENY, BLOCK, "ask"}:
            return {
                "continue": False,
                "user_message": _decision_text(self, request),
            }
        if request.context:
            return {"continue": True, "user_message": request.context}
        return None

    def _followup_output(self, request: _CursorRenderRequest) -> ObjectDict | None:
        message = _append_context(_decision_text(self, request), request.context)
        if message:
            return {"followup_message": message}
        return None

    def _pre_compact_output(self, request: _CursorRenderRequest) -> ObjectDict | None:
        message = _append_context(_decision_text(self, request), request.context)
        if message:
            return {"user_message": message}
        return None

    def _session_start_output(self, request: _CursorRenderRequest) -> ObjectDict | None:
        message = _append_context(_decision_text(self, request), request.context)
        if message:
            return {"additional_context": message}
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
        request = _CursorRenderRequest(
            event_name=render_request.event_name,
            findings=render_request.findings,
            context=render_request.context,
            updated_input=render_request.updated_input,
            decision=render_request.decision,
        )

        if request.event_name in _PERMISSION_EVENTS:
            return self._permission_gate_output(request)

        if request.event_name in _POST_TOOL_EVENTS:
            return self._post_tool_output(request)

        if request.event_name == "UserPromptSubmit":
            return self._prompt_submit_output(request)

        if request.event_name in _FOLLOWUP_EVENTS:
            if request.decision in {DENY, BLOCK, "ask"} or request.context:
                return self._followup_output(request)
            return None

        if request.event_name == "PreCompact":
            return self._pre_compact_output(request)

        if request.event_name == "SessionStart" and request.context:
            return self._session_start_output(request)

        if request.context:
            return {"agent_message": request.context}
        return None
