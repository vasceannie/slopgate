from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from slopgate._types import ObjectDict, object_dict
from slopgate.constants import METADATA_COMMAND

from ._basic import is_edit_like_tool, is_shell_tool
from ._shell import (
    is_mutating_shell_command,
    is_safe_read_shell_command,
    script_write_paths,
    shell_command_paths,
)
from ._shell_paths import shell_write_redirection_paths

ToolIntent = Literal[
    "read",
    "search",
    "list",
    "inspect",
    "mutate",
    "execute",
    "lifecycle",
    "unknown",
]

_READ_TOOL_NAMES = frozenset({"read", "read_file", "before_read_file"})
_SEARCH_TOOL_NAMES = frozenset({"grep", "ripgrep", "rg"})
_LIST_TOOL_NAMES = frozenset({"glob", "ls", "list"})
_INSPECT_TOOL_NAMES = frozenset({"lookat", "look_at", "webfetch", "websearch"})
_TOOL_INTENT_GROUPS: tuple[tuple[frozenset[str], ToolIntent], ...] = (
    (_READ_TOOL_NAMES, "read"),
    (_SEARCH_TOOL_NAMES, "search"),
    (_LIST_TOOL_NAMES, "list"),
    (_INSPECT_TOOL_NAMES, "inspect"),
)
_TOOL_INTENT_BY_NAME: dict[str, ToolIntent] = {
    name: intent for names, intent in _TOOL_INTENT_GROUPS for name in names
}
_LIFECYCLE_EVENTS = frozenset(
    {
        "AfterAgentResponse",
        "AfterAgentThought",
        "CommandExecuted",
        "PermissionReplied",
        "PostCompact",
        "PreCompact",
        "SessionEnd",
        "SessionError",
        "SessionStart",
        "SessionStatus",
        "ShellEnv",
        "Stop",
        "SubagentStart",
        "SubagentStop",
        "UserPromptSubmit",
        "WorkspaceOpen",
    }
)
_MUTATING_PLATFORM_EVENTS = frozenset({"file.edited"})
UNKNOWN_INTENT: ToolIntent = "unknown"
_PLATFORM_EVENT_KEYS = (
    "opencode_hook_event",
    "cursor_hook_event",
    "codex_hook_event",
    "hook_event_name",
    "hookEventName",
    "event_name",
    "event",
)


@runtime_checkable
class _IntentCarrier(Protocol):
    event_name: str
    tool_name: str
    shell_command: str


def _text_from_mapping(mapping: ObjectDict, *keys: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if stripped:
            return stripped
    return ""


def _carrier_text(ctx_or_payload: object, field_name: str) -> str:
    if not isinstance(ctx_or_payload, _IntentCarrier):
        return ""
    if field_name == "event_name":
        return ctx_or_payload.event_name
    if field_name == "tool_name":
        return ctx_or_payload.tool_name
    if field_name == "shell_command":
        return ctx_or_payload.shell_command
    return ""


def _carrier_or_mapping_text(
    ctx_or_payload: object, field_name: str, keys: tuple[str, ...]
) -> str:
    carrier_value = _carrier_text(ctx_or_payload, field_name)
    if carrier_value:
        return carrier_value
    return _text_from_mapping(object_dict(ctx_or_payload), *keys)


def _event_name(ctx_or_payload: object) -> str:
    return _carrier_or_mapping_text(
        ctx_or_payload, "event_name", _PLATFORM_EVENT_KEYS
    )


def _tool_name(ctx_or_payload: object) -> str:
    return _carrier_or_mapping_text(
        ctx_or_payload, "tool_name", ("tool_name", "tool", "toolName")
    )


def _tool_input_mapping(ctx_or_payload: object) -> ObjectDict:
    mapping = object_dict(ctx_or_payload)
    tool_input = object_dict(mapping.get("tool_input"))
    if tool_input:
        return tool_input
    return object_dict(mapping.get("args"))


def _shell_command(ctx_or_payload: object) -> str:
    shell_command = _carrier_text(ctx_or_payload, "shell_command")
    if shell_command:
        return shell_command
    tool_input = _tool_input_mapping(ctx_or_payload)
    return _text_from_mapping(
        tool_input,
        METADATA_COMMAND,
        "script",
        "cmd",
        "powershell_command",
        "pwsh_command",
    )


def _normalized_tool_name(tool_name: str) -> str:
    return tool_name.strip().lower().replace("-", "_")


def _shell_read_intent(command: str) -> ToolIntent:
    lowered = command.lower()
    if any(command_has in lowered for command_has in ("grep", "rg ", "ripgrep")):
        return "search"
    if any(command_has in lowered for command_has in ("ls", "find", "stat")):
        return "list"
    return "read"


def _platform_event_intent(ctx_or_payload: object) -> ToolIntent | None:
    raw_platform_event = platform_event_name(ctx_or_payload)
    if raw_platform_event in _MUTATING_PLATFORM_EVENTS:
        return "mutate"
    if _event_name(ctx_or_payload) in _LIFECYCLE_EVENTS:
        return "lifecycle"
    return None


def _shell_tool_intent(ctx_or_payload: object) -> ToolIntent:
    command = _shell_command(ctx_or_payload)
    if command and is_safe_read_shell_command(command, reject_find_mutation=True):
        return _shell_read_intent(command)
    if command and is_mutating_shell_command(command):
        return "mutate"
    return "execute"


def _named_tool_intent(tool_name: str) -> ToolIntent:
    if is_edit_like_tool(tool_name) or tool_name in {"delete", "remove"}:
        return "mutate"
    return _TOOL_INTENT_BY_NAME.get(tool_name, UNKNOWN_INTENT)


def platform_event_name(ctx_or_payload: object) -> str:
    mapping = object_dict(ctx_or_payload)
    if mapping:
        return _text_from_mapping(mapping, *_PLATFORM_EVENT_KEYS)
    payload = getattr(ctx_or_payload, "payload", None)
    nested = getattr(payload, "payload", None)
    for candidate in (payload, nested):
        candidate_mapping = object_dict(candidate)
        if candidate_mapping:
            return _text_from_mapping(candidate_mapping, *_PLATFORM_EVENT_KEYS)
    return _event_name(ctx_or_payload)


def tool_intent(ctx_or_payload: object) -> ToolIntent:
    platform_intent = _platform_event_intent(ctx_or_payload)
    if platform_intent is not None:
        return platform_intent
    tool_name = _normalized_tool_name(_tool_name(ctx_or_payload))
    if not tool_name:
        return UNKNOWN_INTENT
    if is_shell_tool(tool_name):
        return _shell_tool_intent(ctx_or_payload)
    return _named_tool_intent(tool_name)


def tool_intent_reason(ctx_or_payload: object) -> str:
    intent = tool_intent(ctx_or_payload)
    tool_name = _tool_name(ctx_or_payload) or "unset"
    event_name = _event_name(ctx_or_payload) or "unset"
    if intent == "lifecycle":
        return f"lifecycle_event:{event_name}"
    if intent == "mutate":
        return f"mutation_evidence:{tool_name}"
    if intent in {"read", "search", "list", "inspect"}:
        return f"read_only_tool:{tool_name}"
    if intent == "execute":
        return f"shell_execute:{tool_name}"
    return "unknown_tool_intent"


def is_read_only_tool_use(ctx_or_payload: object) -> bool:
    return tool_intent(ctx_or_payload) in {"read", "search", "list", "inspect"}


def is_mutating_tool_use(ctx_or_payload: object) -> bool:
    return tool_intent(ctx_or_payload) == "mutate"


def candidate_path_source(ctx_or_payload: object) -> str:
    shell_command = _shell_command(ctx_or_payload)
    if shell_command:
        if script_write_paths(shell_command):
            return "script_write_target"
        if shell_write_redirection_paths(shell_command):
            return "redirect_target"
        if shell_command_paths(shell_command):
            return "command_args"
        return "command_text"
    if _tool_input_mapping(ctx_or_payload):
        return "tool_input"
    mapping = object_dict(ctx_or_payload)
    if mapping:
        return "payload"
    return "structured_payload"
