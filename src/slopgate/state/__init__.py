"""Compatibility facade for the former ``state.py`` module."""

from __future__ import annotations

__all__ = [
    "RetryLockPayload",
    "SemanticRetryKey",
    "SemanticRetryLockPayload",
    "SemanticClearRequest",
    "RecoveryEvidenceDraft",
    "RecoveryEvidenceRecord",
    "RecoveryEvidenceError",
    "RECOVERY_EVIDENCE_SCHEMA_VERSION",
    "FirstWriteContractCheck",
    "FirstWriteContractDraft",
    "FirstWriteContractRecord",
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
    "FIRST_WRITE_CONTRACT_SCHEMA_VERSION",
    "FIRST_WRITE_RISK_MAX",
    "FIRST_WRITE_RISK_MIN",
    "FIRST_WRITE_REQUIRED_FIELDS",
    "normalize_contract_operation",
    "normalize_contract_target",
]
from ._models import (
    FirstWriteContractCheck,
    FirstWriteContractDraft,
    FirstWriteContractRecord,
    RecoveryEvidenceDraft,
    RecoveryEvidenceRecord,
    SemanticClearRequest,
    SemanticRetryLockPayload,
    RetryLockPayload,
    SemanticRetryKey,
    DenyKeyPattern,
    HookStateSnapshot,
    IntStateSection,
    ObjectStateSection,
    fcntl,
    msvcrt,
)
from .retry import (
    RECOVERY_EVIDENCE_SCHEMA_VERSION,
    RecoveryEvidenceError,
    RecoveryEvidenceStateMixin,
)
from ._first_write import (
    FIRST_WRITE_CONTRACT_SCHEMA_VERSION,
    FIRST_WRITE_RISK_MAX,
    FIRST_WRITE_RISK_MIN,
    FIRST_WRITE_REQUIRED_FIELDS,
    FirstWriteContractStateMixin,
    normalize_contract_operation,
    normalize_contract_target,
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
from . import _locks_store
from ._locks_store import (
    RepairPlanStateMixin,
    RetryLockStateMixin,
    failure_count,
)


class HookStateStore(
    FirstWriteContractStateMixin,
    RecoveryEvidenceStateMixin,
    _locks_store.HookStateStore,
):
    """Persistent hook state including first-write contracts."""
