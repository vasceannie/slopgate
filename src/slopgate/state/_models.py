"""Persistent hook-state store."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType
from typing import Literal, TypedDict
from slopgate._types import (
    ObjectDict,
)


def _optional_module(name: str) -> ModuleType | None:
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        return None


fcntl = _optional_module("fcntl")
msvcrt = _optional_module("msvcrt")


@dataclass(frozen=True, slots=True)
class RetryLockPayload:
    repeated_rule_ids: list[str]
    current_rule_ids: list[str]
    paths: list[str]
    attempt_fingerprint: str | None
    count: int


@dataclass(frozen=True, slots=True)
class SemanticRetryKey:
    session_id: str
    repo_root: str
    rule_id: str
    path: str | None
    operation_category: str | None


@dataclass(frozen=True, slots=True)
class SemanticRetryLockPayload:
    key: SemanticRetryKey
    attempt_fingerprint: str | None
    count: int


@dataclass(frozen=True, slots=True)
class SemanticClearRequest:
    session_id: str
    repo_root: str
    touched_paths: frozenset[str]
    operation_category: str
    active_keys: frozenset[str]


@dataclass(frozen=True, slots=True)
class RecoveryEvidenceDraft:
    session_id: str
    repo_root: str
    violated_invariant: str
    previous_design_failure: str
    new_design: str
    verification: str


@dataclass(frozen=True, slots=True)
class RecoveryEvidenceRecord:
    target_paths: tuple[str, ...]
    locked_rules: tuple[str, ...]
    files_reread_after_lock: tuple[str, ...]
    created_at: int
    schema_version: int


@dataclass(frozen=True, slots=True)
class DenyKeyPattern:
    session_id: str
    rule_id: str
    path: str | None
    attempt_fingerprint: str | None


@dataclass(frozen=True, slots=True)
class FirstWriteContractDraft:
    session_id: str
    target: str
    operation: str
    reuse_convention: str
    stable_behavior_api: str
    predicted_risks: tuple[str, ...]
    design_response: str
    focused_verification: str


@dataclass(frozen=True, slots=True)
class FirstWriteContractRecord:
    target: str
    operation: str
    timestamp: int
    schema_version: int


@dataclass(frozen=True, slots=True)
class FirstWriteContractCheck:
    target: str
    operation: str
    status: str
    missing_fields: tuple[str, ...]
    authorized: bool = False

    @property
    def complete(self) -> bool:
        return not self.missing_fields and self.status in {"ready", "authorized"}


class HookStateSnapshot(TypedDict):
    full_reads: dict[str, int]
    search_reminders: dict[str, int]
    deny_hits: dict[str, int]
    advisory_hits: dict[str, ObjectDict]
    retry_locks: dict[str, ObjectDict]
    repair_plans: dict[str, ObjectDict]
    first_write_contracts: dict[str, ObjectDict]
    semantic_deny_hits: dict[str, ObjectDict]
    recovery_evidence: dict[str, ObjectDict]
    full_read_events: dict[str, ObjectDict]
    event_sequence: int


ObjectStateSection = Literal["retry_locks", "repair_plans", "first_write_contracts"]
IntStateSection = Literal["search_reminders"]
