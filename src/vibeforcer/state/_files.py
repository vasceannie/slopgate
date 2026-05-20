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
from vibeforcer._types import (
    ObjectDict,
    ObjectMapping,
    object_dict,
)
from vibeforcer.util.logger import warning

from ._models import _HookStateSnapshot as _HookStateSnapshot, fcntl as fcntl, msvcrt as msvcrt


class _StateFileMixin:
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


class _StateSnapshotMixin(_StateFileMixin):
    _TTL_SECONDS: int

    def _load_state(self) -> _HookStateSnapshot:
        cutoff = int(time()) - self._TTL_SECONDS
        state = self._read_state_file()
        full_reads = self._coerce_recent_int_map(state.get("full_reads"), cutoff)
        search_reminders = self._coerce_recent_int_map(state.get("search_reminders"), cutoff)
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
                yield key, value

    @classmethod
    def _coerce_recent_int_map(cls, raw: object, cutoff: int) -> dict[str, int]:
        return {key: value for key, value in cls._iter_int_items(raw) if value >= cutoff}

    @classmethod
    def _coerce_counter_map(cls, raw: object) -> dict[str, int]:
        return {key: value for key, value in cls._iter_int_items(raw) if value >= 0}

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
