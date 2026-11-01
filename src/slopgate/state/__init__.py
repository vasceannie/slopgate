"""Compatibility facade for the former ``state.py`` module."""

from __future__ import annotations

__all__ = [
    "RetryLockPayload",
    "DenyKeyPattern",
    "HookStateSnapshot",
    "RepairRequiredPayload",
    "RepairTarget",
    "IntStateSection",
    "ObjectStateSection",
    "fcntl",
    "msvcrt",
    "StateFileMixin",
    "StateSnapshotMixin",
    "HookStateCorruptionError",
    "AdvisoryHitStateMixin",
    "DenyHitStateMixin",
    "FullReadStateMixin",
    "SearchReminderStateMixin",
    "SessionMutationStateMixin",
    "SessionStateMutationMixin",
    "StateKeyMixin",
    "HookStateStore",
    "RepairPlanStateMixin",
    "RetryLockStateMixin",
    "failure_count",
]
from ._models import (
    RetryLockPayload,
    RepairRequiredPayload,
    RepairTarget,
    DenyKeyPattern,
    HookStateSnapshot,
    IntStateSection,
    ObjectStateSection,
    fcntl,
    msvcrt,
)
from ._files import HookStateCorruptionError, StateFileMixin, StateSnapshotMixin
from ._keys import (
    AdvisoryHitStateMixin,
    DenyHitStateMixin,
    FullReadStateMixin,
    SearchReminderStateMixin,
    SessionMutationStateMixin,
    SessionStateMutationMixin,
    StateKeyMixin,
)
from ._locks_store import (
    HookStateStore,
    RepairPlanStateMixin,
    RetryLockStateMixin,
    failure_count,
)
