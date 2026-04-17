from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from time import time
from types import ModuleType
from typing import TextIO, TypedDict

from vibeforcer._types import (
    ObjectDict,
    ObjectMapping,
    bool_value,
    object_dict,
    object_list,
    string_value,
)
from vibeforcer.util.logger import warning

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


class HookStateStore:
    """Persist small cross-hook state under the trace dir.

    Hooks run as separate subprocesses in production, so even the first
    stateful features need a disk-backed store. Keep it tiny and scoped.
    """

    _TTL_SECONDS = 3600

    def __init__(self, trace_dir: Path) -> None:
        self._path = trace_dir / "hook-state.json"
        self._lock_path = trace_dir / "hook-state.lock"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def has_full_read(self, session_id: str, path: str) -> bool:
        key = self._full_read_key(session_id, path)
        state = self._load_state()
        return key in state["full_reads"]

    def should_emit_search_reminder(self, session_id: str) -> bool:
        key = self._session_key(session_id)
        state = self._load_state()
        return key not in state["search_reminders"]

    def record_search_reminder(self, session_id: str) -> None:
        key = self._session_key(session_id)
        with self._locked_state():
            state = self._load_state()
            state["search_reminders"][key] = int(time())
            self._save_state(state)

    def record_full_read(self, session_id: str, path: str) -> None:
        normalized_path = self._normalize_path(path)
        if not Path(normalized_path).exists():
            return
        key = self._full_read_key(session_id, normalized_path)
        with self._locked_state():
            state = self._load_state()
            state["full_reads"][key] = int(time())
            self._save_state(state)

    def record_deny_hit(
        self,
        session_id: str,
        rule_id: str,
        path: str | None = None,
        attempt_fingerprint: str | None = None,
    ) -> int:
        key = self._deny_key(session_id, rule_id, path, attempt_fingerprint)
        with self._locked_state():
            state = self._load_state()
            deny_hits = state["deny_hits"]
            count = deny_hits.get(key, 0) + 1
            deny_hits[key] = count
            self._save_state(state)
        return count

    def clear_deny_hit(
        self,
        session_id: str,
        rule_id: str,
        path: str | None = None,
        attempt_fingerprint: str | None = None,
    ) -> None:
        with self._locked_state():
            state = self._load_state()
            deny_hits = state["deny_hits"]
            keys_to_clear = [
                key
                for key in deny_hits
                if self._deny_key_matches(
                    key,
                    session_id=session_id,
                    rule_id=rule_id,
                    path=path,
                    attempt_fingerprint=attempt_fingerprint,
                )
            ]
            for key in keys_to_clear:
                _ = deny_hits.pop(key, None)
            self._save_state(state)

    def recent_repeated_failures(
        self,
        session_id: str,
        limit: int = 5,
    ) -> list[ObjectDict]:
        key_prefix = self._session_key(session_id)
        state = self._load_state()
        deny_hits = state["deny_hits"]
        pairs: list[ObjectDict] = []
        for key, count in deny_hits.items():
            if count < 2:
                continue
            try:
                parsed = object_dict(json.loads(key))
            except json.JSONDecodeError:
                continue
            if string_value(parsed.get("session_id")) != key_prefix:
                continue
            rule_id = string_value(parsed.get("rule_id"))
            if rule_id is None:
                continue
            path = string_value(parsed.get("path")) or "__pathless__"
            pairs.append({"rule_id": rule_id, "path": path, "count": count})
        pairs.sort(key=_failure_count, reverse=True)
        return pairs[:limit]

    def set_retry_lock(
        self,
        session_id: str,
        *,
        repeated_rule_ids: list[str],
        current_rule_ids: list[str],
        paths: list[str],
        attempt_fingerprint: str | None,
        count: int,
    ) -> None:
        key = self._session_key(session_id)
        with self._locked_state():
            state = self._load_state()
            state["retry_locks"][key] = {
                "repeated_rule_ids": repeated_rule_ids,
                "current_rule_ids": current_rule_ids,
                "paths": [self._normalize_path(path) for path in paths if path],
                "attempt_fingerprint": attempt_fingerprint,
                "count": count,
                "timestamp": int(time()),
            }
            self._save_state(state)

    def get_retry_lock(self, session_id: str) -> ObjectDict | None:
        key = self._session_key(session_id)
        state = self._load_state()
        raw = state["retry_locks"].get(key)
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
        key = self._session_key(session_id)
        with self._locked_state():
            state = self._load_state()
            _ = state["retry_locks"].pop(key, None)
            self._save_state(state)

    def mark_repair_plan(
        self, session_id: str, constraints_named: bool, reread_done: bool
    ) -> None:
        key = self._session_key(session_id)
        with self._locked_state():
            state = self._load_state()
            state["repair_plans"][key] = {
                "constraints_named": constraints_named,
                "reread_done": reread_done,
                "timestamp": int(time()),
            }
            self._save_state(state)

    def has_repair_plan(self, session_id: str) -> bool:
        key = self._session_key(session_id)
        state = self._load_state()
        raw = state["repair_plans"].get(key)
        if raw is None:
            return False
        return (
            bool_value(raw.get("constraints_named")) is True
            and bool_value(raw.get("reread_done")) is True
        )

    @contextmanager
    def _locked_state(self) -> Iterator[None]:
        with self._lock_path.open("a+", encoding="utf-8") as handle:
            self._acquire_lock(handle)
            try:
                yield
            finally:
                self._release_lock(handle)

    def _acquire_lock(self, handle: TextIO) -> None:
        fileno = handle.fileno()
        if fcntl is not None:
            fcntl.flock(fileno, fcntl.LOCK_EX)
            return
        if msvcrt is not None:  # pragma: no cover - Windows only
            handle.seek(0)
            handle.write("\0")
            handle.flush()
            handle.seek(0)
            msvcrt.locking(fileno, msvcrt.LK_LOCK, 1)

    def _release_lock(self, handle: TextIO) -> None:
        fileno = handle.fileno()
        if fcntl is not None:
            fcntl.flock(fileno, fcntl.LOCK_UN)
            return
        if msvcrt is not None:  # pragma: no cover - Windows only
            handle.seek(0)
            msvcrt.locking(fileno, msvcrt.LK_UNLCK, 1)

    def _full_read_key(self, session_id: str, path: str) -> str:
        return json.dumps(
            {"session_id": session_id.strip(), "path": self._normalize_path(path.strip())},
            sort_keys=True,
        )

    def _deny_key(
        self,
        session_id: str,
        rule_id: str,
        path: str | None,
        attempt_fingerprint: str | None,
    ) -> str:
        normalized_path = self._normalize_path(path) if path else "__pathless__"
        return json.dumps(
            {
                "session_id": self._session_key(session_id),
                "rule_id": rule_id.strip(),
                "path": normalized_path,
                "attempt_fingerprint": attempt_fingerprint or "__unknown_attempt__",
            },
            sort_keys=True,
        )

    def _deny_key_matches(
        self,
        key: str,
        *,
        session_id: str,
        rule_id: str,
        path: str | None,
        attempt_fingerprint: str | None,
    ) -> bool:
        try:
            parsed = object_dict(json.loads(key))
        except json.JSONDecodeError:
            return False
        if string_value(parsed.get("session_id")) != self._session_key(session_id):
            return False
        if string_value(parsed.get("rule_id")) != rule_id.strip():
            return False
        expected_path = self._normalize_path(path) if path else "__pathless__"
        if string_value(parsed.get("path")) != expected_path:
            return False
        if attempt_fingerprint is None:
            return True
        return string_value(parsed.get("attempt_fingerprint")) == attempt_fingerprint

    def _session_key(self, session_id: str) -> str:
        return session_id.strip()

    def _normalize_path(self, path: str) -> str:
        try:
            return str(Path(path).resolve(strict=False))
        except OSError:
            return str(Path(path).absolute())

    def _load_state(self) -> _HookStateSnapshot:
        cutoff = int(time()) - self._TTL_SECONDS
        state = self._read_state_file()
        full_reads = self._coerce_full_reads(state.get("full_reads"), cutoff)
        search_reminders = self._coerce_int_map(state.get("search_reminders"), cutoff)
        deny_hits = self._coerce_counter_map(state.get("deny_hits"))
        retry_locks = self._coerce_object_map(state.get("retry_locks"), cutoff)
        repair_plans = self._coerce_object_map(state.get("repair_plans"), cutoff)
        return {
            "full_reads": full_reads,
            "search_reminders": search_reminders,
            "deny_hits": deny_hits,
            "retry_locks": retry_locks,
            "repair_plans": repair_plans,
        }

    def _read_state_file(self) -> ObjectDict:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError):
            return {}
        return object_dict(raw)

    @staticmethod
    def _coerce_full_reads(raw_full_reads: object, cutoff: int) -> dict[str, int]:
        full_reads: dict[str, int] = {}
        for key, timestamp in object_dict(raw_full_reads).items():
            if isinstance(timestamp, int) and timestamp >= cutoff:
                full_reads[key] = timestamp
        return full_reads

    @staticmethod
    def _coerce_int_map(raw: object, cutoff: int) -> dict[str, int]:
        out: dict[str, int] = {}
        for key, value in object_dict(raw).items():
            if not isinstance(value, int):
                continue
            if value >= cutoff:
                out[key] = value
        return out

    @staticmethod
    def _coerce_counter_map(raw: object) -> dict[str, int]:
        out: dict[str, int] = {}
        for key, value in object_dict(raw).items():
            if isinstance(value, int) and value >= 0:
                out[key] = value
        return out

    @staticmethod
    def _coerce_object_map(raw: object, cutoff: int) -> dict[str, ObjectDict]:
        out: dict[str, ObjectDict] = {}
        for key, value in object_dict(raw).items():
            typed = object_dict(value)
            timestamp = typed.get("timestamp")
            if not isinstance(timestamp, int) or timestamp < cutoff:
                continue
            out[key] = typed
        return out

    def _save_state(self, state: ObjectMapping) -> None:
        fd, tmp_name = tempfile.mkstemp(
            prefix="hook-state-", suffix=".json", dir=str(self._path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, sort_keys=True)
            os.replace(tmp_name, self._path)
        finally:
            try:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            except OSError as exc:
                warning("hook state temp cleanup failed", path=tmp_name, error=str(exc))


class _HookStateSnapshot(TypedDict):
    full_reads: dict[str, int]
    search_reminders: dict[str, int]
    deny_hits: dict[str, int]
    retry_locks: dict[str, ObjectDict]
    repair_plans: dict[str, ObjectDict]


def _failure_count(item: ObjectDict) -> int:
    count = item.get("count")
    return count if isinstance(count, int) else 0
