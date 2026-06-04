"""Compatibility facade for the former ``state.py`` module."""

from __future__ import annotations

from ._models import RetryLockPayload as RetryLockPayload, _DenyKeyPattern as _DenyKeyPattern, _HookStateSnapshot as _HookStateSnapshot, _IntStateSection as _IntStateSection, _ObjectStateSection as _ObjectStateSection, fcntl as fcntl, msvcrt as msvcrt
from ._files import _StateFileMixin as _StateFileMixin, _StateSnapshotMixin as _StateSnapshotMixin
from ._keys import _DenyHitStateMixin as _DenyHitStateMixin, _FullReadStateMixin as _FullReadStateMixin, _SearchReminderStateMixin as _SearchReminderStateMixin, _SessionStateMutationMixin as _SessionStateMutationMixin, _StateKeyMixin as _StateKeyMixin
from ._locks_store import HookStateStore as HookStateStore, _RepairPlanStateMixin as _RepairPlanStateMixin, _RetryLockStateMixin as _RetryLockStateMixin, _failure_count as _failure_count
