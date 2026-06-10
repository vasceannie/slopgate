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
class DenyKeyPattern:
    session_id: str
    rule_id: str
    path: str | None
    attempt_fingerprint: str | None


class HookStateSnapshot(TypedDict):
    full_reads: dict[str, int]
    search_reminders: dict[str, int]
    deny_hits: dict[str, int]
    retry_locks: dict[str, ObjectDict]
    repair_plans: dict[str, ObjectDict]


ObjectStateSection = Literal["retry_locks", "repair_plans"]
IntStateSection = Literal["search_reminders"]
