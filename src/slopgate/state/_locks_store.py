"""Persistent hook-state store."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
from time import time
from slopgate._types import ObjectDict, bool_value, object_list, string_value
from slopgate.constants import (
    METADATA_FUNCTION,
    METADATA_PATH,
    REPAIR_TARGET_ERROR,
    RULE_ID_KEY,
    WORKTREE_KEY,
)
from ._keys import (
    AdvisoryHitStateMixin,
    DenyHitStateMixin,
    FullReadStateMixin,
    SearchReminderStateMixin,
    StateKeyMixin,
)
from ._files import StateSnapshotMixin
from ._models import RepairRequiredPayload, RepairTarget, RetryLockPayload


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
    def _repair_target_record(self, target: RepairTarget) -> ObjectDict:
        return {
            RULE_ID_KEY: target.rule_id,
            METADATA_PATH: self._normalize_path(target.path) if target.path else None,
            "raw_path": target.raw_path,
            METADATA_FUNCTION: target.function,
            REPAIR_TARGET_ERROR: target.error,
        }

    def _repair_target_records(self, targets: list[RepairTarget]) -> list[ObjectDict]:
        records = [self._repair_target_record(target) for target in targets]
        return sorted(records, key=lambda item: json.dumps(item, sort_keys=True))

    def repair_generation(
        self,
        *,
        targets: list[RepairTarget],
        event_identity: str = "",
    ) -> str:
        material = json.dumps(
            {
                "event_identity": event_identity.strip(),
                "targets": self._repair_target_records(targets),
                WORKTREE_KEY: self._scope,
            },
            sort_keys=True,
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
        if payload.worktree != self._scope:
            raise ValueError("repair payload worktree does not match state scope")
        targets = self._repair_target_records(payload.targets)
        with self._locked_state():
            state = self._load_state()
            state["repair_required"] = {
                "status": "REPAIR_REQUIRED",
                "generation": generation,
                "session_id": payload.session_id,
                "call_id": payload.call_id,
                WORKTREE_KEY: self._scope,
                "targets": targets,
                "rule_ids": sorted({str(target[RULE_ID_KEY]) for target in targets}),
                "paths": sorted(
                    str(target[METADATA_PATH])
                    for target in targets
                    if isinstance(target.get(METADATA_PATH), str)
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

    @property
    def scope(self) -> str:
        return self._scope

    def __init__(
        self,
        trace_dir: Path,
        *,
        scope: str | None = None,
        path_base: str | Path | None = None,
    ) -> None:
        raw_scope = scope.strip() if isinstance(scope, str) else ""
        scope_path = Path(raw_scope) if raw_scope else None
        if (
            scope_path is not None
            and not scope_path.is_absolute()
            and path_base is None
        ):
            raise ValueError("relative state scope requires an explicit path base")
        raw_path_base = (
            Path(path_base)
            if path_base is not None
            else scope_path
            if scope_path is not None
            else Path.cwd()
        )
        try:
            self._path_base = raw_path_base.resolve(strict=False)
        except OSError:
            self._path_base = raw_path_base.absolute()
        if scope_path is not None and not scope_path.is_absolute():
            scope_path = self._path_base / scope_path
        self._scope = str(scope_path.resolve()) if scope_path is not None else ""
        if self._scope:
            digest = hashlib.sha256(self._scope.encode("utf-8")).hexdigest()
            state_name = f"hook-state-{digest[:_STATE_SCOPE_DIGEST_LENGTH]}.json"
        else:
            state_name = "hook-state.json"
        self._path = trace_dir / state_name
        self._lock_path = trace_dir / "hook-state.lock"
        self._path.parent.mkdir(parents=True, exist_ok=True)


def failure_count(item: ObjectDict) -> int:
    count = item.get("count")
    return count if isinstance(count, int) else 0
