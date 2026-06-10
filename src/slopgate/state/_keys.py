"""Persistent hook-state store."""

from __future__ import annotations
import json
from pathlib import Path
from time import time
from slopgate.constants import METADATA_PATH, SESSION_ID
from slopgate._types import ObjectDict, ObjectMapping, object_dict, string_value
from ._files import StateSnapshotMixin
from ._models import (
    DenyKeyPattern,
    HookStateSnapshot,
    IntStateSection,
    ObjectStateSection,
)


def failure_count(item: ObjectDict) -> int:
    count = item.get("count")
    return count if isinstance(count, int) else 0


class StateKeyMixin:
    def _full_read_key(self, session_id: str, path: str) -> str:
        return json.dumps(
            {
                SESSION_ID: session_id.strip(),
                METADATA_PATH: self._normalize_path(path.strip()),
            },
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
                SESSION_ID: session_id.strip(),
                "rule_id": rule_id.strip(),
                METADATA_PATH: normalized_path,
                "attempt_fingerprint": attempt_fingerprint or "__unknown_attempt__",
            },
            sort_keys=True,
        )

    def _deny_key_matches(self, key: str, pattern: DenyKeyPattern) -> bool:
        try:
            parsed = object_dict(json.loads(key))
        except json.JSONDecodeError:
            return False
        if string_value(parsed.get(SESSION_ID)) != pattern.session_id.strip():
            return False
        if string_value(parsed.get("rule_id")) != pattern.rule_id.strip():
            return False
        expected_path = (
            self._normalize_path(pattern.path) if pattern.path else "__pathless__"
        )
        if string_value(parsed.get(METADATA_PATH)) != expected_path:
            return False
        if pattern.attempt_fingerprint is None:
            return True
        return (
            string_value(parsed.get("attempt_fingerprint"))
            == pattern.attempt_fingerprint
        )

    def _object_state_entry(
        self, state: HookStateSnapshot, section: ObjectStateSection, session_id: str
    ) -> ObjectDict | None:
        return state[section].get(session_id.strip())

    def _mark_recent_int_entry(
        self, state: HookStateSnapshot, section: IntStateSection, session_id: str
    ) -> None:
        state[section][session_id.strip()] = int(time())

    def _normalize_path(self, path: str) -> str:
        try:
            return str(Path(path).resolve(strict=False))
        except OSError:
            return str(Path(path).absolute())


__all__ = [
    "DenyHitStateMixin",
    "FullReadStateMixin",
    "SearchReminderStateMixin",
    "SessionStateMutationMixin",
]


class SessionStateMutationMixin(StateKeyMixin, StateSnapshotMixin):
    def _write_object_state_entry(
        self, section: ObjectStateSection, session_id: str, values: ObjectMapping
    ) -> None:
        with self._locked_state():
            state = self._load_state()
            state[section][session_id.strip()] = {
                **object_dict(values),
                "timestamp": int(time()),
            }
            self._save_state(state)


class FullReadStateMixin(StateKeyMixin, StateSnapshotMixin):
    def has_full_read(self, session_id: str, path: str) -> bool:
        key = self._full_read_key(session_id, path)
        state = self._load_state()
        return key in state["full_reads"]

    def record_full_read(self, session_id: str, path: str) -> None:
        normalized_path = self._normalize_path(path)
        if not Path(normalized_path).exists():
            return
        key = self._full_read_key(session_id, normalized_path)
        with self._locked_state():
            state = self._load_state()
            state["full_reads"][key] = int(time())
            self._save_state(state)


class SearchReminderStateMixin(StateKeyMixin, StateSnapshotMixin):
    _STOP_QUALITY_REMINDER_PREFIX = "stop-quality-reminder:"

    def should_emit_search_reminder(self, session_id: str) -> bool:
        key = session_id.strip()
        state = self._load_state()
        return key not in state["search_reminders"]

    def record_search_reminder(self, session_id: str) -> None:
        with self._locked_state():
            state = self._load_state()
            self._mark_recent_int_entry(state, "search_reminders", session_id)
            self._save_state(state)

    def _stop_quality_reminder_key(self, session_id: str) -> str:
        return f"{self._STOP_QUALITY_REMINDER_PREFIX}{session_id.strip()}"

    def should_emit_stop_quality_reminder(self, session_id: str) -> bool:
        key = self._stop_quality_reminder_key(session_id)
        state = self._load_state()
        return key not in state["search_reminders"]

    def record_stop_quality_reminder(self, session_id: str) -> None:
        key = self._stop_quality_reminder_key(session_id)
        with self._locked_state():
            state = self._load_state()
            self._mark_recent_int_entry(state, "search_reminders", key)
            self._save_state(state)


class DenyHitStateMixin(StateKeyMixin, StateSnapshotMixin):
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
            state["deny_hits"] = self._prune_counter_map(deny_hits, {key})
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
            if attempt_fingerprint is not None:
                key = self._deny_key(session_id, rule_id, path, attempt_fingerprint)
                _ = deny_hits.pop(key, None)
                state["deny_hits"] = self._prune_counter_map(deny_hits)
                self._save_state(state)
                return
            keys_to_clear = [
                key
                for key in deny_hits
                if self._deny_key_matches(
                    key,
                    DenyKeyPattern(
                        session_id=session_id,
                        rule_id=rule_id,
                        path=path,
                        attempt_fingerprint=attempt_fingerprint,
                    ),
                )
            ]
            for key in keys_to_clear:
                _ = deny_hits.pop(key, None)
            state["deny_hits"] = self._prune_counter_map(deny_hits)
            self._save_state(state)

    def recent_repeated_failures(
        self, session_id: str, limit: int = 5
    ) -> list[ObjectDict]:
        key_prefix = session_id.strip()
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
            if string_value(parsed.get(SESSION_ID)) != key_prefix:
                continue
            rule_id = string_value(parsed.get("rule_id"))
            if rule_id is None:
                continue
            path = string_value(parsed.get(METADATA_PATH)) or "__pathless__"
            pairs.append({"rule_id": rule_id, METADATA_PATH: path, "count": count})
        pairs.sort(key=failure_count, reverse=True)
        return pairs[:limit]
