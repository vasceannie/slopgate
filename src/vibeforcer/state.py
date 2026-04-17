from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from time import time
from types import ModuleType
from typing import TextIO, cast

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
        return key in state.get("full_reads", {})

    def should_emit_search_reminder(self, session_id: str) -> bool:
        key = self._session_key(session_id)
        state = self._load_state()
        return key not in state.get("search_reminders", {})

    def record_search_reminder(self, session_id: str) -> None:
        key = self._session_key(session_id)
        with self._locked_state():
            state = self._load_state()
            state.setdefault("search_reminders", {})[key] = int(time())
            self._save_state(state)

    def record_full_read(self, session_id: str, path: str) -> None:
        normalized_path = self._normalize_path(path)
        if not Path(normalized_path).exists():
            return
        key = self._full_read_key(session_id, normalized_path)
        with self._locked_state():
            state = self._load_state()
            state.setdefault("full_reads", {})[key] = int(time())
            self._save_state(state)

    def record_deny_hit(
        self,
        session_id: str,
        rule_id: str,
        path: str | None = None,
    ) -> int:
        key = self._deny_key(session_id, rule_id, path)
        with self._locked_state():
            state = self._load_state()
            deny_hits = state.setdefault("deny_hits", {})
            count = deny_hits.get(key, 0) + 1
            deny_hits[key] = count
            self._save_state(state)
        return count

    def clear_deny_hit(
        self,
        session_id: str,
        rule_id: str,
        path: str | None = None,
    ) -> None:
        key = self._deny_key(session_id, rule_id, path)
        with self._locked_state():
            state = self._load_state()
            deny_hits = state.setdefault("deny_hits", {})
            _ = deny_hits.pop(key, None)
            self._save_state(state)

    def recent_repeated_failures(
        self,
        session_id: str,
        limit: int = 5,
    ) -> list[dict[str, object]]:
        key_prefix = self._session_key(session_id)
        state = self._load_state()
        deny_hits = state.get("deny_hits", {})
        pairs: list[dict[str, object]] = []
        for key, count in deny_hits.items():
            if not isinstance(key, str) or not isinstance(count, int) or count < 2:
                continue
            try:
                parsed = json.loads(key)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, Mapping):
                continue
            if parsed.get("session_id") != key_prefix:
                continue
            rule_id = parsed.get("rule_id")
            if not isinstance(rule_id, str):
                continue
            path = parsed.get("path")
            if not isinstance(path, str):
                path = "__pathless__"
            pairs.append({"rule_id": rule_id, "path": path, "count": count})
        pairs.sort(
            key=lambda item: int(cast(int, item.get("count", 0))),
            reverse=True,
        )
        return pairs[:limit]

    def set_retry_lock(
        self, session_id: str, rule_id: str, path: str | None, count: int
    ) -> None:
        key = self._session_key(session_id)
        with self._locked_state():
            state = self._load_state()
            state.setdefault("retry_locks", {})[key] = {
                "rule_id": rule_id,
                "path": self._normalize_path(path) if path else "__pathless__",
                "count": count,
                "timestamp": int(time()),
            }
            self._save_state(state)

    def get_retry_lock(self, session_id: str) -> dict[str, object] | None:
        key = self._session_key(session_id)
        state = self._load_state()
        raw = state.get("retry_locks", {}).get(key)
        if not isinstance(raw, Mapping):
            return None
        return {
            "rule_id": raw.get("rule_id"),
            "path": raw.get("path"),
            "count": raw.get("count"),
        }

    def clear_retry_lock(self, session_id: str) -> None:
        key = self._session_key(session_id)
        with self._locked_state():
            state = self._load_state()
            _ = state.setdefault("retry_locks", {}).pop(key, None)
            self._save_state(state)

    def mark_repair_plan(
        self, session_id: str, constraints_named: bool, reread_done: bool
    ) -> None:
        key = self._session_key(session_id)
        with self._locked_state():
            state = self._load_state()
            state.setdefault("repair_plans", {})[key] = {
                "constraints_named": constraints_named,
                "reread_done": reread_done,
                "timestamp": int(time()),
            }
            self._save_state(state)

    def has_repair_plan(self, session_id: str) -> bool:
        key = self._session_key(session_id)
        state = self._load_state()
        raw = state.get("repair_plans", {}).get(key)
        if not isinstance(raw, Mapping):
            return False
        return bool(raw.get("constraints_named")) and bool(raw.get("reread_done"))

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

    def _deny_key(self, session_id: str, rule_id: str, path: str | None) -> str:
        normalized_path = self._normalize_path(path) if path else "__pathless__"
        return json.dumps(
            {
                "session_id": self._session_key(session_id),
                "rule_id": rule_id.strip(),
                "path": normalized_path,
            },
            sort_keys=True,
        )

    def _session_key(self, session_id: str) -> str:
        return session_id.strip()

    def _normalize_path(self, path: str) -> str:
        try:
            return str(Path(path).resolve(strict=False))
        except OSError:
            return str(Path(path).absolute())

    def _load_state(self) -> dict[str, object]:
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

    def _read_state_file(self) -> dict[str, object]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, Mapping):
            return {}
        result: dict[str, object] = {}
        for key, value in cast(Mapping[object, object], raw).items():
            if isinstance(key, str):
                result[key] = value
        return result

    @staticmethod
    def _coerce_full_reads(raw_full_reads: object, cutoff: int) -> dict[str, int]:
        if not isinstance(raw_full_reads, Mapping):
            return {}
        full_reads: dict[str, int] = {}
        for key, timestamp in cast(Mapping[object, object], raw_full_reads).items():
            if isinstance(key, str) and isinstance(timestamp, int) and timestamp >= cutoff:
                full_reads[key] = timestamp
        return full_reads

    @staticmethod
    def _coerce_int_map(raw: object, cutoff: int) -> dict[str, int]:
        if not isinstance(raw, Mapping):
            return {}
        out: dict[str, int] = {}
        for key, value in cast(Mapping[object, object], raw).items():
            if not isinstance(key, str) or not isinstance(value, int):
                continue
            if value >= cutoff:
                out[key] = value
        return out

    @staticmethod
    def _coerce_counter_map(raw: object) -> dict[str, int]:
        if not isinstance(raw, Mapping):
            return {}
        out: dict[str, int] = {}
        for key, value in cast(Mapping[object, object], raw).items():
            if isinstance(key, str) and isinstance(value, int) and value >= 0:
                out[key] = value
        return out

    @staticmethod
    def _coerce_object_map(raw: object, cutoff: int) -> dict[str, dict[str, object]]:
        if not isinstance(raw, Mapping):
            return {}
        out: dict[str, dict[str, object]] = {}
        for key, value in cast(Mapping[object, object], raw).items():
            if not isinstance(key, str) or not isinstance(value, Mapping):
                continue
            typed = cast(Mapping[object, object], value)
            timestamp = typed.get("timestamp")
            if not isinstance(timestamp, int) or timestamp < cutoff:
                continue
            inner: dict[str, object] = {}
            for inner_key, inner_value in typed.items():
                if isinstance(inner_key, str):
                    inner[inner_key] = inner_value
            out[key] = inner
        return out

    def _save_state(self, state: dict[str, object]) -> None:
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
