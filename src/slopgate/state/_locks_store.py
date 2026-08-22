"""Persistent hook-state store."""

from __future__ import annotations
import hashlib
from pathlib import Path
from time import time
from slopgate._types import ObjectDict, bool_value, object_list, string_value
from ._keys import (
    AdvisoryHitStateMixin,
    DenyHitStateMixin,
    FullReadStateMixin,
    SearchReminderStateMixin,
    StateKeyMixin,
)
from ._files import StateSnapshotMixin
from ._models import RepairRequiredPayload, RetryLockPayload


_STATE_SCOPE_DIGEST_LENGTH = 16


class RetryLockStateMixin(StateKeyMixin, StateSnapshotMixin):
    def set_retry_lock(self, session_id: str, *, payload: RetryLockPayload) -> None:
        with self._locked_state():
            state = self._load_state()
            state["retry_locks"][session_id.strip()] = {
                "repeated_rule_ids": payload.repeated_rule_ids,
                "current_rule_ids": payload.current_rule_ids,
                "paths": [self._normalize_path(path) for path in payload.paths if path],
                "attempt_fingerprint": payload.attempt_fingerprint,
                "count": payload.count,
                "timestamp": int(time()),
            }
            self._save_state(state)

    def get_retry_lock(self, session_id: str) -> ObjectDict | None:
        state = self._load_state()
        raw = state["retry_locks"].get(session_id.strip())
        if raw is None:
            return None
        result: ObjectDict = {}
        repeated_rule_ids = [
            item
            for item in object_list(raw.get("repeated_rule_ids"))
            if isinstance(item, str)
        ]
        current_rule_ids = [
            item
            for item in object_list(raw.get("current_rule_ids"))
            if isinstance(item, str)
        ]
        paths = [
            item for item in object_list(raw.get("paths")) if isinstance(item, str)
        ]
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


class RepairPlanStateMixin(StateKeyMixin, StateSnapshotMixin):
    def repair_generation(
        self,
        *,
        rule_ids: list[str],
        paths: list[str],
        event_identity: str = "",
    ) -> str:
        normalized_paths = sorted(
            self._normalize_path(path) for path in paths if path
        )
        material = "\n".join(
            [*sorted(set(rule_ids)), *normalized_paths, event_identity.strip()]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def mark_repair_plan(
        self, session_id: str, constraints_named: bool, reread_done: bool
    ) -> None:
        with self._locked_state():
            state = self._load_state()
            state["repair_plans"][session_id.strip()] = {
                "constraints_named": constraints_named,
                "reread_done": reread_done,
                "timestamp": int(time()),
            }
            self._save_state(state)

    def has_repair_plan(self, session_id: str) -> bool:
        state = self._load_state()
        raw = state["repair_plans"].get(session_id.strip())
        if raw is None:
            return False
        return (
            bool_value(raw.get("constraints_named")) is True
            and bool_value(raw.get("reread_done")) is True
        )

    def mark_repair_required(
        self,
        generation: str,
        payload: RepairRequiredPayload,
    ) -> None:
        with self._locked_state():
            state = self._load_state()
            state["repair_required"] = {
                "status": "REPAIR_REQUIRED",
                "generation": generation,
                "session_id": payload.session_id,
                "call_id": payload.call_id,
                "rule_ids": sorted(set(payload.rule_ids)),
                "paths": sorted(
                    self._normalize_path(path) for path in payload.paths if path
                ),
                "timestamp": int(time()),
            }
            self._save_state(state)

    def get_repair_required(self) -> ObjectDict | None:
        with self._locked_state():
            state = self._load_state()
            required = state["repair_required"]
            return dict(required) if required else None

    def clear_repair_required(self, generation: str) -> bool:
        with self._locked_state():
            state = self._load_state()
            required = state["repair_required"]
            if required.get("generation") != generation:
                return False
            state["repair_required"] = {}
            self._save_state(state)
            return True


class HookStateStore(
    FullReadStateMixin,
    SearchReminderStateMixin,
    AdvisoryHitStateMixin,
    DenyHitStateMixin,
    RetryLockStateMixin,
    RepairPlanStateMixin,
):
    """Persist small cross-hook state under the trace dir.

    Hooks run as separate subprocesses in production, so even the first
    stateful features need a disk-backed store. Keep it tiny and scoped.
    """

    _TTL_SECONDS = 3600

    def __init__(self, trace_dir: Path, *, scope: str | None = None) -> None:
        raw_scope = scope.strip() if isinstance(scope, str) else ""
        normalized_scope = str(Path(raw_scope).resolve()) if raw_scope else ""
        if normalized_scope:
            digest = hashlib.sha256(normalized_scope.encode("utf-8")).hexdigest()
            state_name = f"hook-state-{digest[:_STATE_SCOPE_DIGEST_LENGTH]}.json"
        else:
            state_name = "hook-state.json"
        self._path = trace_dir / state_name
        self._lock_path = trace_dir / "hook-state.lock"
        self._path.parent.mkdir(parents=True, exist_ok=True)


def failure_count(item: ObjectDict) -> int:
    count = item.get("count")
    return count if isinstance(count, int) else 0
