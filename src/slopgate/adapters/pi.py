"""Pi Agent adapter — translates pi lifecycle events into slopgate's canonical format.

Pi events and their canonical mapping:
  tool_call (write/edit/bash)  →  PreToolUse
  tool_result                  →  PostToolUse
  tool_execution_end (exit 0)  →  PostToolUse
  tool_execution_end (non-zero)→  PostToolUseFailure
  user_bash                    →  PreToolUse
  input                        →  UserPromptSubmit
  before_agent_start           →  SessionStart
  turn_end                     →  TurnEnd
  agent_end                    →  Stop
"""

from __future__ import annotations

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
    canonical_payload_with_event,
    merge_standard_session_fields,
    sync_tool_result_fields,
)
from slopgate.adapters.base import PlatformAdapter, render_request_from_call
from slopgate.constants import (
    ASK,
    BLOCK,
    DENY,
    METADATA_COMMAND,
    METADATA_SLOPGATE,
    METADATA_TOOL_NAME,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    SESSION_START,
    STOP,
)

# Pi canonical event names
PI_EVENT_NAMES: set[str] = {
    PRE_TOOL_USE,  # tool_call → PreToolUse
    PERMISSION_REQUEST,  # (not directly used by pi)
    POST_TOOL_USE,  # tool_result → PostToolUse (success)
    "PostToolUseFailure",  # tool_execution_end → PostToolUseFailure (non-zero exit)
    SESSION_START,  # before_agent_start
    "UserPromptSubmit",  # input
    STOP,  # agent_end
    "TurnEnd",  # turn_end
}

_PI_EVENT_ALIASES: dict[str, str] = {
    "tool_call": PRE_TOOL_USE,
    "user_bash": PRE_TOOL_USE,
    "tool_result": POST_TOOL_USE,
    "tool_execution_end": POST_TOOL_USE,
    "input": "UserPromptSubmit",
    "before_agent_start": SESSION_START,
    "turn_end": "TurnEnd",
    "agent_end": STOP,
}

# Pi tool names → slopgate constant tool names
_PI_TOOL_MAP: dict[str, str] = {
    "write": "Write",
    "edit": "Edit",
    "bash": "Bash",
    "read": "Read",
    "grep": "Grep",
    "glob": "Glob",
    "webfetch": "WebFetch",
    "websearch": "WebSearch",
}


def _raw_event_name(raw: ObjectMapping) -> str:
    event = string_value(raw.get("hook_event_name")) or string_value(
        raw.get("hookEventName")
    )
    if event is None:
        return ""
    return event.lower().replace("-", "")


def _canonical_event_name(raw: ObjectMapping) -> str:
    """Map the pi event name to a slopgate canonical event."""
    return canonical_event_name(raw, PI_EVENT_NAMES, _PI_EVENT_ALIASES)


def _canonical_tool_name(raw: ObjectMapping) -> str:
    """Map the pi tool name to a slopgate canonical tool name."""
    tool = (
        string_value(raw.get(METADATA_TOOL_NAME))
        or string_value(raw.get("toolName"))
        or string_value(raw.get("tool"))
        or string_value(raw.get("name"))
    )
    if not tool:
        return ""
    normalized = tool.lower().strip()
    return _PI_TOOL_MAP.get(normalized, tool)


def _sync_tool_input(raw: ObjectMapping, canonical: ObjectDict) -> None:
    if is_object_dict(canonical.get("tool_input")):
        return
    for key in ("input", "args", "arguments"):
        value = raw.get(key)
        if is_object_dict(value):
            canonical["tool_input"] = object_dict(value)
            return


def _sync_user_bash_command(raw: ObjectMapping, canonical: ObjectDict) -> None:
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


class PiAdapter(PlatformAdapter):
    """Pi Agent adapter translating pi lifecycle events into slopgate's canonical format."""

    name: str = "pi"

    @override
    def normalize_payload(self, raw: ObjectMapping) -> ObjectDict:
        canonical = canonical_payload_with_event(raw, _canonical_event_name(raw))

        tool_name = _canonical_tool_name(raw)
        if tool_name:
            canonical[METADATA_TOOL_NAME] = tool_name

        _sync_tool_input(raw, canonical)
        _sync_user_bash_command(raw, canonical)
        merge_standard_session_fields(raw, canonical)
        sync_tool_result_fields(canonical)
        return canonical

    @override
    def render_output(
        self,
        *args: object,
        **kwargs: object,
    ) -> ObjectDict | None:
        """Render findings into Pi extension return data."""
        render_request = render_request_from_call(args, kwargs)
        if not render_request.findings:
            return None

        output: ObjectDict = {}
        can_block = render_request.event_name in {PRE_TOOL_USE, "UserPromptSubmit"}
        if can_block and render_request.decision in {DENY, BLOCK, ASK}:
            output[BLOCK] = True
            output["reason"] = self.join_messages(
                self.decision_findings(render_request.findings, render_request.decision)
            )
        if render_request.decision == "allow" and render_request.updated_input:
            output["updated_input"] = render_request.updated_input
        if render_request.context:
            output["context"] = render_request.context
        if render_request.event_name == POST_TOOL_USE and output:
            output["tool_result_patch"] = {
                "details": {
                    METADATA_SLOPGATE: {
                        "decision": render_request.decision,
                        "context": render_request.context,
                        "reason": output.get("reason"),
                    }
                }
            }
        return output or None
