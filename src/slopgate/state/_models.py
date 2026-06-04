"""Persistent hook-state store."""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Literal, TypedDict
from slopgate._types import (
    ObjectDict,
)


fcntl: ModuleType | None
try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - Windows only
    fcntl = None
else:
    fcntl = _fcntl

msvcrt: ModuleType | None
try:
    import msvcrt as _msvcrt
except ImportError:  # pragma: no cover - POSIX only
    msvcrt = None
else:
    msvcrt = _msvcrt


@dataclass(frozen=True, slots=True)
class RetryLockPayload:
    repeated_rule_ids: list[str]
    current_rule_ids: list[str]
    paths: list[str]
    attempt_fingerprint: str | None
    count: int


@dataclass(frozen=True, slots=True)
class _DenyKeyPattern:
    session_id: str
    rule_id: str
    path: str | None
    attempt_fingerprint: str | None


class _HookStateSnapshot(TypedDict):
    full_reads: dict[str, int]
    search_reminders: dict[str, int]
    deny_hits: dict[str, int]
    retry_locks: dict[str, ObjectDict]
    repair_plans: dict[str, ObjectDict]


_ObjectStateSection = Literal["retry_locks", "repair_plans"]
_IntStateSection = Literal["search_reminders"]
