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

from slopgate._types import ObjectDict, ObjectMapping
from slopgate.adapters._payload_fields import (
    canonical_event_name,
    canonical_payload_with_event,
    merge_standard_session_fields,
    sync_tool_result_fields,
)
from slopgate.adapters._session_identity import SESSION_IDENTITY_TELEMETRY
from slopgate.adapters.base import PlatformAdapter, render_request_from_call
from slopgate.adapters.omp import (
    _canonical_tool_name,
    _sync_tool_input,
    _sync_user_bash_command,
)
from slopgate.constants import (
    ASK,
    BLOCK,
    DENY,
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

def _canonical_event_name(raw: ObjectMapping) -> str:
    """Map the pi event name to a slopgate canonical event."""
    SESSION_IDENTITY_TELEMETRY.record_metric("pi.event.canonical_name")
    return canonical_event_name(raw, PI_EVENT_NAMES, _PI_EVENT_ALIASES)


class PiAdapter(PlatformAdapter):
    """Pi Agent adapter translating pi lifecycle events into slopgate's canonical format."""

    name: str = "pi"

    @override
    def normalize_payload(self, raw: ObjectMapping) -> ObjectDict:
        SESSION_IDENTITY_TELEMETRY.record_metric("pi.normalize_payload")
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
        SESSION_IDENTITY_TELEMETRY.record_metric("pi.render_output")
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
