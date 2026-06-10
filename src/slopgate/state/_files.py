"""Persistent hook-state store."""

from __future__ import annotations
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from time import time
from typing import TextIO
from slopgate._types import ObjectDict, ObjectMapping, object_dict
from slopgate.util.logger import warning
from ._models import HookStateSnapshot, fcntl, msvcrt


class StateFileMixin:
    _path: Path
    _lock_path: Path

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
        if msvcrt is not None:
            handle.seek(0)
            handle.write("\x00")
            handle.flush()
            handle.seek(0)
            msvcrt.locking(fileno, msvcrt.LK_LOCK, 1)

    def _release_lock(self, handle: TextIO) -> None:
        fileno = handle.fileno()
        if fcntl is not None:
            fcntl.flock(fileno, fcntl.LOCK_UN)
            return
        if msvcrt is not None:
            handle.seek(0)
            msvcrt.locking(fileno, msvcrt.LK_UNLCK, 1)

    def _read_state_file(self) -> ObjectDict:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError):
            return {}
        return object_dict(raw)

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


__all__ = ["StateSnapshotMixin"]


class StateSnapshotMixin(StateFileMixin):
    _TTL_SECONDS: int
    _MAX_DENY_HITS = 512

    def _load_state(self) -> HookStateSnapshot:
        cutoff = int(time()) - self._TTL_SECONDS
        state = self._read_state_file()
        full_reads = self._coerce_recent_int_map(state.get("full_reads"), cutoff)
        search_reminders = self._coerce_recent_int_map(
            state.get("search_reminders"), cutoff
        )
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

    @staticmethod
    def _iter_int_items(raw: object) -> Iterator[tuple[str, int]]:
        for key, value in object_dict(raw).items():
            if isinstance(value, int):
                yield (key, value)

    @classmethod
    def _coerce_recent_int_map(cls, raw: object, cutoff: int) -> dict[str, int]:
        return {
            key: value for key, value in cls._iter_int_items(raw) if value >= cutoff
        }

    @classmethod
    def _coerce_counter_map(cls, raw: object) -> dict[str, int]:
        counters = {key: value for key, value in cls._iter_int_items(raw) if value >= 0}
        return cls._prune_counter_map(counters)

    @classmethod
    def _prune_counter_map(
        cls, counters: dict[str, int], protected_keys: set[str] | None = None
    ) -> dict[str, int]:
        if len(counters) <= cls._MAX_DENY_HITS:
            return dict(counters)
        protected = {
            key: value
            for key, value in counters.items()
            if protected_keys is not None and key in protected_keys
        }
        slots = max(cls._MAX_DENY_HITS - len(protected), 0)
        ranked = sorted(
            ((key, value) for key, value in counters.items() if key not in protected),
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )
        selected = dict(ranked[:slots])
        selected.update(protected)
        return selected

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
