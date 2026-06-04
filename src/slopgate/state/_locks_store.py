"""Persistent hook-state store."""

from __future__ import annotations

from pathlib import Path
from slopgate._types import (
    ObjectDict,
    bool_value,
    object_list,
    string_value,
)

from ._keys import _DenyHitStateMixin as _DenyHitStateMixin, _FullReadStateMixin as _FullReadStateMixin, _SearchReminderStateMixin as _SearchReminderStateMixin, _SessionStateMutationMixin as _SessionStateMutationMixin
from ._models import RetryLockPayload as RetryLockPayload


class _RetryLockStateMixin(_SessionStateMutationMixin):
    def set_retry_lock(
        self,
        session_id: str,
        *,
        payload: RetryLockPayload,
    ) -> None:
        self._write_object_state_entry(
            "retry_locks",
            session_id,
            {
                "repeated_rule_ids": payload.repeated_rule_ids,
                "current_rule_ids": payload.current_rule_ids,
                "paths": [self._normalize_path(path) for path in payload.paths if path],
                "attempt_fingerprint": payload.attempt_fingerprint,
                "count": payload.count,
            },
        )

    def get_retry_lock(self, session_id: str) -> ObjectDict | None:
        state = self._load_state()
        raw = self._object_state_entry(state, "retry_locks", session_id)
        if raw is None:
            return None
        result: ObjectDict = {}
        repeated_rule_ids = [
            item for item in object_list(raw.get("repeated_rule_ids")) if isinstance(item, str)
        ]
        current_rule_ids = [
            item for item in object_list(raw.get("current_rule_ids")) if isinstance(item, str)
        ]
        paths = [item for item in object_list(raw.get("paths")) if isinstance(item, str)]
        attempt_fingerprint = string_value(raw.get("attempt_fingerprint"))
        count = raw.get("count")
        if repeated_rule_ids:
            result["repeated_rule_ids"] = repeated_rule_ids
        if current_rule_ids:
            result["current_rule_ids"] = current_rule_ids
        if paths:
            result["paths"] = paths
        if attempt_fingerprint is not None:
            result["attempt_fingerprint"] = attempt_fingerprint
        if isinstance(count, int):
            result["count"] = count
        return result

    def clear_retry_lock(self, session_id: str) -> None:
        key = session_id.strip()
        with self._locked_state():
            state = self._load_state()
            _ = state["retry_locks"].pop(key, None)
            self._save_state(state)


class _RepairPlanStateMixin(_SessionStateMutationMixin):
    def mark_repair_plan(
        self, session_id: str, constraints_named: bool, reread_done: bool
    ) -> None:
        self._write_object_state_entry(
            "repair_plans",
            session_id,
            {"constraints_named": constraints_named, "reread_done": reread_done},
        )

    def has_repair_plan(self, session_id: str) -> bool:
        state = self._load_state()
        raw = self._object_state_entry(state, "repair_plans", session_id)
        if raw is None:
            return False
        return (
            bool_value(raw.get("constraints_named")) is True
            and bool_value(raw.get("reread_done")) is True
        )


class HookStateStore(
    _FullReadStateMixin,
    _SearchReminderStateMixin,
    _DenyHitStateMixin,
    _RetryLockStateMixin,
    _RepairPlanStateMixin,
):

    """Persist small cross-hook state under the trace dir.

    Hooks run as separate subprocesses in production, so even the first
    stateful features need a disk-backed store. Keep it tiny and scoped.
    """

    _TTL_SECONDS = 3600

    def __init__(self, trace_dir: Path) -> None:
        self._path = trace_dir / "hook-state.json"
        self._lock_path = trace_dir / "hook-state.lock"
        self._path.parent.mkdir(parents=True, exist_ok=True)


def _failure_count(item: ObjectDict) -> int:
    count = item.get("count")
    return count if isinstance(count, int) else 0
