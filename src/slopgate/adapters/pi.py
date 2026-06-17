"""Pi Agent adapter — translates pi lifecycle events into slopgate's canonical format.

Pi events and their canonical mapping:
  tool_call (write/edit/bash)  →  PreToolUse
  tool_result                  →  PostToolUse
  tool_execution_end           →  PostToolUse (async)
  input                        →  UserPromptSubmit
  before_agent_start           →  SessionStart
  turn_end                     →  TurnEnd
  agent_end                    →  Stop
"""

from __future__ import annotations

from typing_extensions import override

from slopgate._types import ObjectDict, ObjectMapping, is_object_dict, object_dict, string_value
from slopgate.adapters._payload_fields import merge_standard_session_fields, sync_tool_result_fields
from slopgate.adapters.base import PlatformAdapter
from slopgate.constants import (
    BLOCK,
    DENY,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
)

# Pi canonical event names
PI_EVENT_NAMES: set[str] = {
    PRE_TOOL_USE,       # tool_call → PreToolUse
    PERMISSION_REQUEST,  # (not directly used by pi)
    POST_TOOL_USE,       # tool_result / tool_execution_end → PostToolUse
    "SessionStart",      # before_agent_start
    "UserPromptSubmit",  # input
    "Stop",              # agent_end
    "TurnEnd",           # turn_end
}

_PI_EVENT_ALIASES: dict[str, str] = {
    "tool_call": PRE_TOOL_USE,
    "tool_result": POST_TOOL_USE,
    "tool_execution_end": POST_TOOL_USE,
    "input": "UserPromptSubmit",
    "before_agent_start": "SessionStart",
    "turn_end": "TurnEnd",
    "agent_end": "Stop",
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


def _canonical_event_name(raw: ObjectMapping) -> str:
    """Map the pi event name to a slopgate canonical event."""
    event = string_value(raw.get("hook_event_name")) or string_value(
        raw.get("hookEventName")
    )
    if not event:
        return ""
    if event in PI_EVENT_NAMES:
        return event
    return _PI_EVENT_ALIASES.get(event.lower().replace("-", ""), event)


def _canonical_tool_name(raw: ObjectMapping) -> str:
    """Map the pi tool name to a slopgate canonical tool name."""
    tool = string_value(raw.get("tool_name")) or string_value(raw.get("tool"))
    if not tool:
        return ""
    normalized = tool.lower().strip()
    return _PI_TOOL_MAP.get(normalized, tool)


class PiAdapter(PlatformAdapter):
    """Pi Agent adapter translating pi lifecycle events into slopgate's canonical format."""

    name: str = "pi"

    @override
    def normalize_payload(self, raw: ObjectMapping) -> ObjectDict:
        canonical = object_dict(raw) if is_object_dict(raw) else object_dict(raw)

        event_name = _canonical_event_name(raw)
        if event_name:
            canonical["hook_event_name"] = event_name

        tool_name = _canonical_tool_name(raw)
        if tool_name:
            canonical["tool_name"] = tool_name

        merge_standard_session_fields(raw, canonical)
        sync_tool_result_fields(canonical)
        return canonical

    @override
    def render_output(
        self,
        *args: object,
        **kwargs: object,
    ) -> ObjectDict | None:
        """Render findings as a structured JSON result for the pi extension.

        Returns a dict with:
          - findings: list of serialized findings
          - decisions: map of rule_id → decision
          - has_blockers: whether any finding blocks execution
          - context: additional context for the agent
        """
        from slopgate.adapters.base import render_request_from_call
        from slopgate.models import RuleFinding

        render_request = render_request_from_call(args, kwargs)
        if not render_request.findings:
            return None

        blocking = [f for f in render_request.findings if f.decision in (DENY, BLOCK)]
        warnings = [f for f in render_request.findings if f.decision is None]
        decisions_map: dict[str, str | None] = {}
        for f in render_request.findings:
            decisions_map[f.rule_id] = f.decision

        serialized = [
            {
                "rule_id": f.rule_id,
                "title": f.title,
                "severity": f.severity.as_name() if hasattr(f.severity, "as_name") else str(f.severity),
                "message": f.message,
                "decision": f.decision,
                "additional_context": f.additional_context,
                "metadata": f.metadata,
            }
            for f in render_request.findings
        ]

        out: ObjectDict = {
            "findings": serialized,
            "decisions": decisions_map,
            "has_blockers": len(blocking) > 0,
            "has_warnings": len(warnings) > 0,
            "blocking_count": len(blocking),
            "total_findings": len(render_request.findings),
        }

        if render_request.context:
            out["context"] = render_request.context

        if render_request.decision in (DENY, BLOCK):
            context_lines = [
                "[slopgate] Action blocked:",
            ]
            for f in blocking:
                context_lines.append(f"  - {f.rule_id}: {f.message}")
            out["reason"] = "\n".join(context_lines)

        return out
