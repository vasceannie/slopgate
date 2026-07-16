"""Semantic retry counters, locks, and read evidence."""

from __future__ import annotations

import json
from time import time

from slopgate._types import ObjectDict, object_dict
from slopgate.constants import METADATA_PATH, SESSION_ID

from .._models import (
    DenyKeyPattern,
    HookStateSnapshot,
    SemanticClearRequest,
    SemanticRetryKey,
    SemanticRetryLockPayload,
)
from ._identity import parse_semantic_key
from .read_evidence import RetryReadEvidenceMixin


class SemanticRetryStoreMixin(RetryReadEvidenceMixin):
    def semantic_state_key(self, key: SemanticRetryKey) -> str:
        normalized_path = self._normalize_path(key.path) if key.path else None
        normalized_repo = self._normalize_path(key.repo_root)
        identity = {
            SESSION_ID: key.session_id.strip(),
            "repo_root": normalized_repo,
            "rule_id": key.rule_id.strip(),
            METADATA_PATH: normalized_path,
            "operation_category": key.operation_category,
        }
        return json.dumps(identity, sort_keys=True)

    def record_semantic_deny(
        self, key: SemanticRetryKey, attempt_fingerprint: str | None
    ) -> tuple[int, int]:
        semantic_key = self.semantic_state_key(key)
        exact_key = self._rule_path_state_key(
            key.session_id,
            key.rule_id,
            key.path,
            {"attempt_fingerprint": attempt_fingerprint or "__unknown_attempt__"},
        )
        with self._locked_state():
            state = self._load_state()
            exact_count = state["deny_hits"].get(exact_key, 0) + 1
            state["deny_hits"][exact_key] = exact_count
            existing = object_dict(state["semantic_deny_hits"].get(semantic_key))
            raw_count = existing.get("count")
            semantic_count = (raw_count if isinstance(raw_count, int) else 0) + 1
            state["semantic_deny_hits"][semantic_key] = {
                "count": semantic_count,
                "timestamp": int(time()),
            }
            state["semantic_deny_hits"] = self._prune_semantic_entries(
                state["semantic_deny_hits"], semantic_key
            )
            state["deny_hits"] = self._prune_counter_map(
                state["deny_hits"], {exact_key}
            )
            self._save_state(state)
        return semantic_count, exact_count

    def set_semantic_retry_lock(self, payload: SemanticRetryLockPayload) -> None:
        key = self.semantic_state_key(payload.key)
        with self._locked_state():
            state = self._load_state()
            sequence = state["event_sequence"] + 1
            state["retry_locks"][key] = {
                "rule_id": payload.key.rule_id,
                "repo_root": self._normalize_path(payload.key.repo_root),
                METADATA_PATH: (
                    self._normalize_path(payload.key.path) if payload.key.path else None
                ),
                "operation_category": payload.key.operation_category,
                "attempt_fingerprint": payload.attempt_fingerprint,
                "count": payload.count,
                "sequence": sequence,
                "timestamp": int(time()),
            }
            state["event_sequence"] = sequence
            self._save_state(state)

    def active_semantic_retry_locks(
        self, session_id: str, repo_root: str
    ) -> dict[str, ObjectDict]:
        normalized_repo = self._normalize_path(repo_root)
        result: dict[str, ObjectDict] = {}
        for raw_key, lock in self._load_state()["retry_locks"].items():
            parsed = parse_semantic_key(raw_key)
            if parsed is None or parsed.session_id != session_id.strip():
                continue
            if parsed.repo_root == normalized_repo:
                result[raw_key] = lock
        return result

    def clear_resolved_semantic_denials(self, request: SemanticClearRequest) -> None:
        normalized_repo = self._normalize_path(request.repo_root)
        normalized_paths = {
            self._normalize_path(path) for path in request.touched_paths
        }
        with self._locked_state():
            state = self._load_state()
            keys_to_clear: list[str] = []
            for raw_key in state["semantic_deny_hits"]:
                parsed = parse_semantic_key(raw_key)
                if parsed is None or parsed.session_id != request.session_id.strip():
                    continue
                if parsed.repo_root != normalized_repo:
                    continue
                target_matches = (
                    parsed.path in normalized_paths
                    if parsed.path is not None
                    else parsed.operation_category == request.operation_category
                )
                if target_matches and raw_key not in request.active_keys:
                    keys_to_clear.append(raw_key)
            for raw_key in keys_to_clear:
                parsed = parse_semantic_key(raw_key)
                _ = state["semantic_deny_hits"].pop(raw_key, None)
                _ = state["retry_locks"].pop(raw_key, None)
                if parsed is not None:
                    self._clear_exact_hits(state, parsed)
            self._save_state(state)

    def clear_semantic_retry_locks(self, raw_keys: set[str]) -> None:
        with self._locked_state():
            state = self._load_state()
            for raw_key in raw_keys:
                parsed = parse_semantic_key(raw_key)
                _ = state["retry_locks"].pop(raw_key, None)
                _ = state["semantic_deny_hits"].pop(raw_key, None)
                if parsed is not None:
                    self._clear_exact_hits(state, parsed)
            self._save_state(state)

    def recent_semantic_failures(
        self, session_id: str, limit: int = 5
    ) -> list[ObjectDict]:
        failures: list[ObjectDict] = []
        for raw_key, entry in self._load_state()["semantic_deny_hits"].items():
            parsed = parse_semantic_key(raw_key)
            count = object_dict(entry).get("count")
            if parsed is None or parsed.session_id != session_id.strip():
                continue
            if not isinstance(count, int) or count < 2:
                continue
            failures.append(
                {
                    "rule_id": parsed.rule_id,
                    METADATA_PATH: parsed.path or "__pathless__",
                    "count": count,
                }
            )
        failures.sort(
            key=lambda item: (
                item.get("count") if isinstance(item.get("count"), int) else 0,
                str(item.get("rule_id", "")),
            ),
            reverse=True,
        )
        return failures[:limit]

    def _prune_semantic_entries(
        self, entries: dict[str, ObjectDict], protected_key: str
    ) -> dict[str, ObjectDict]:
        if len(entries) <= self._MAX_DENY_HITS:
            return dict(entries)
        protected = entries.get(protected_key)
        slots = self._MAX_DENY_HITS - (1 if protected is not None else 0)
        ranked = sorted(
            ((key, value) for key, value in entries.items() if key != protected_key),
            key=lambda item: (
                object_dict(item[1]).get("count", 0),
                object_dict(item[1]).get("timestamp", 0),
                item[0],
            ),
            reverse=True,
        )
        selected = dict(ranked[:slots])
        if protected is not None:
            selected[protected_key] = protected
        return selected

    def _clear_exact_hits(
        self, state: HookStateSnapshot, key: SemanticRetryKey
    ) -> None:
        pattern = DenyKeyPattern(key.session_id, key.rule_id, key.path, None)
        deny_hits = state["deny_hits"]
        exact_keys = [raw for raw in deny_hits if self._deny_key_matches(raw, pattern)]
        for raw in exact_keys:
            _ = deny_hits.pop(raw, None)
