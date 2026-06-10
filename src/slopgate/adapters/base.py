"""Base adapter protocol for platform-specific input/output translation."""

from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast
from slopgate._types import ObjectDict, ObjectMapping, object_dict
from slopgate.constants import BLOCK, DENY
from slopgate.models import RuleFinding
from slopgate.rules.base import join_messages

_PERMISSION_REQUEST_DECISIONS = frozenset({DENY, "allow", BLOCK, "ask"})


@dataclass(frozen=True, slots=True)
class RenderRequest:
    event_name: str
    findings: list[RuleFinding]
    context: str | None
    updated_input: ObjectDict
    decision: str | None


def render_request_from_call(
    args: tuple[object, ...], kwargs: dict[str, object]
) -> RenderRequest:
    if len(args) != 2:
        raise TypeError("render_output expects event_name and findings")
    event_name, findings = args
    if not isinstance(event_name, str):
        raise TypeError("event_name must be a string")
    if not isinstance(findings, list):
        raise TypeError("findings must be a list")
    context_value = kwargs.pop("context", None)
    updated_input_value = kwargs.pop("updated_input", None)
    decision_value = kwargs.pop("decision", None)
    if kwargs:
        unexpected = ", ".join(sorted(kwargs))
        raise TypeError(f"unexpected render_output keyword(s): {unexpected}")
    return RenderRequest(
        event_name=event_name,
        findings=[
            finding
            for finding in cast("list[object]", findings)
            if isinstance(finding, RuleFinding)
        ],
        context=context_value if isinstance(context_value, str) else None,
        updated_input=object_dict(updated_input_value),
        decision=decision_value if isinstance(decision_value, str) else None,
    )


def hook_specific_context_output(event_name: str, context: str) -> ObjectDict:
    """Render shared Claude/Codex hook-specific context output."""
    return {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": context,
        }
    }


def render_permission_request_output(
    event_name: str,
    decision: str | None,
    reason: str,
    updated_input: ObjectDict | None = None,
) -> ObjectDict | None:
    """Render shared Claude/Codex PermissionRequest decision output."""
    if decision not in _PERMISSION_REQUEST_DECISIONS:
        return None
    if decision == "allow":
        behavior = "allow"
    elif decision == "ask":
        behavior = "ask"
    else:
        behavior = DENY
    inner: ObjectDict = {"behavior": behavior}
    if updated_input and decision == "allow":
        inner["updatedInput"] = updated_input
    if behavior in {DENY, "ask"}:
        inner["message"] = reason
    return {"hookSpecificOutput": {"hookEventName": event_name, "decision": inner}}


class PlatformAdapter(ABC):
    name: str = ""

    @abstractmethod
    def normalize_payload(self, raw: ObjectMapping) -> ObjectDict:
        """Convert a raw platform payload into canonical form."""

    @abstractmethod
    def render_output(self, *args: object, **kwargs: object) -> ObjectDict | None:
        """Render findings into platform-native JSON for stdout."""

    join_messages: Callable[[list[RuleFinding]], str] = staticmethod(join_messages)

    @staticmethod
    def decision_findings(
        findings: list[RuleFinding], decision: str | None
    ) -> list[RuleFinding]:
        return [f for f in findings if f.decision == decision]
