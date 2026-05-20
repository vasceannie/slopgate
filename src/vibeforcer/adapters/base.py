"""Base adapter protocol for platform-specific input/output translation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from vibeforcer._types import ObjectDict, ObjectMapping
from vibeforcer.constants import BLOCK, DENY
from vibeforcer.models import RuleFinding
from vibeforcer.rules.base import join_messages as _join_messages

_PERMISSION_REQUEST_DECISIONS = frozenset({DENY, "allow", BLOCK, "ask"})


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
    behavior = "allow" if decision == "allow" else DENY
    inner: ObjectDict = {"behavior": behavior}
    if updated_input and decision == "allow":
        inner["updatedInput"] = updated_input
    if behavior == DENY:
        inner["message"] = reason
    return {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "decision": inner,
        }
    }


class PlatformAdapter(ABC):
    name: str = ""

    @abstractmethod
    def normalize_payload(self, raw: ObjectMapping) -> ObjectDict:
        """Convert a raw platform payload into canonical form."""

    @abstractmethod
    def render_output(
        self,
        event_name: str,
        findings: list[RuleFinding],
        *,
        context: str | None = None,
        updated_input: ObjectDict | None = None,
        decision: str | None = None,
    ) -> ObjectDict | None:
        """Render findings into platform-native JSON for stdout."""

    join_messages: Callable[[list[RuleFinding]], str] = staticmethod(_join_messages)

    @staticmethod
    def decision_findings(
        findings: list[RuleFinding], decision: str | None
    ) -> list[RuleFinding]:
        return [f for f in findings if f.decision == decision]
