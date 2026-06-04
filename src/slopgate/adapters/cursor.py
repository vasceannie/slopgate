"""Cursor adapter for native Cursor hooks.

Output shapes follow https://cursor.com/docs/agent/hooks — notably
``beforeSubmitPrompt`` uses ``continue``/``user_message``, ``postToolUse`` uses
``additional_context`` (no hard deny), and ``stop``/``subagentStop`` use
``followup_message``.
"""

from __future__ import annotations

from typing_extensions import override

from slopgate._types import ObjectDict, ObjectMapping, object_dict, string_value
from slopgate.adapters._payload_fields import merge_session_id, sync_tool_result_fields
from slopgate.adapters.base import PlatformAdapter
from slopgate.adapters.cursor_output import (
    cursor_render_request_from_call,
    render_cursor_output,
)
from slopgate.constants import METADATA_COMMAND

_CURSOR_EVENT_MAP: dict[str, str] = {
    "preToolUse": "PreToolUse",
    "postToolUse": "PostToolUse",
    "postToolUseFailure": "PostToolUseFailure",
    "beforeShellExecution": "PreToolUse",
    "afterShellExecution": "PostToolUse",
    "beforeMCPExecution": "PreToolUse",
    "afterMCPExecution": "PostToolUse",
    "beforeReadFile": "PreToolUse",
    "beforeTabFileRead": "PreToolUse",
    "afterFileEdit": "PostToolUse",
    "afterTabFileEdit": "PostToolUse",
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
    command = _first_string(raw, METADATA_COMMAND, "cmd", "script") or _first_string(
        tool_input, METADATA_COMMAND, "cmd", "script"
    )
    if command:
        tool_input = dict(tool_input)
        tool_input.setdefault(METADATA_COMMAND, command)
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


class CursorAdapter(PlatformAdapter):
    name: str = "cursor"

    @override
    def normalize_payload(self, raw: ObjectMapping) -> ObjectDict:
        canonical = object_dict(raw)
        cursor_event = _first_string(raw, "hook_event_name", "hookEventName", "event_name", "event")
        canonical["hook_event_name"] = _CURSOR_EVENT_MAP.get(cursor_event, cursor_event)
        if cursor_event:
            canonical["cursor_hook_event"] = cursor_event

        merge_session_id(
            raw,
            canonical,
            extra_keys=("conversation_id", "conversationId"),
        )
        _workspace_cwd(raw, canonical)

        tool_name = _tool_name_from_raw(raw, cursor_event)
        if tool_name:
            canonical["tool_name"] = tool_name
        tool_input = _cursor_tool_input(raw, cursor_event)
        if tool_input:
            canonical["tool_input"] = tool_input

        if cursor_event in _FILE_EDIT_EVENTS and "tool_response" not in canonical:
            canonical["tool_response"] = {"file_path": tool_input.get("file_path", "")}
        sync_tool_result_fields(canonical, raw)

        prompt = _first_string(raw, "prompt", "user_prompt", "userPrompt")
        if prompt:
            canonical["prompt"] = prompt
        return canonical

    @override
    def render_output(
        self,
        *args: object,
        **kwargs: object,
    ) -> ObjectDict | None:
        request = cursor_render_request_from_call(args, kwargs)
        return render_cursor_output(self, request)
