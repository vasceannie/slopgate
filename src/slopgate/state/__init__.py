"""Compatibility facade for the former ``state.py`` module."""

from __future__ import annotations

__all__ = [
    "RetryLockPayload",
    "DenyKeyPattern",
    "HookStateSnapshot",
    "IntStateSection",
    "ObjectStateSection",
    "fcntl",
    "msvcrt",
    "StateFileMixin",
    "StateSnapshotMixin",
    "AdvisoryHitStateMixin",
    "DenyHitStateMixin",
    "FullReadStateMixin",
    "SearchReminderStateMixin",
    "SessionStateMutationMixin",
    "StateKeyMixin",
    "HookStateStore",
    "RepairPlanStateMixin",
    "RetryLockStateMixin",
    "failure_count",
]
from ._models import (
    RetryLockPayload,
    DenyKeyPattern,
    HookStateSnapshot,
    IntStateSection,
    ObjectStateSection,
    fcntl,
    msvcrt,
)
from ._files import StateFileMixin, StateSnapshotMixin
from ._keys import (
    AdvisoryHitStateMixin,
    DenyHitStateMixin,
    FullReadStateMixin,
    SearchReminderStateMixin,
    SessionStateMutationMixin,
    StateKeyMixin,
)
from ._locks_store import (
    HookStateStore,
    RepairPlanStateMixin,
    RetryLockStateMixin,
    failure_count,
)
