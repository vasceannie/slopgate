"""Structured recovery evidence lifecycle."""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import time

from slopgate._types import ObjectDict, object_dict, object_list, string_value
from slopgate.constants import METADATA_PATH, SESSION_ID

from .._models import RecoveryEvidenceDraft, RecoveryEvidenceRecord
from ._identity import materially_different_design, parse_semantic_key
from ._store import SemanticRetryStoreMixin


RECOVERY_EVIDENCE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class RecoveryEvidenceError(Exception):
    code: str

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class _RecoveryScope:
    target_paths: list[str]
    locked_rules: list[str]
    reread_paths: list[str]


class RecoveryEvidenceStateMixin(SemanticRetryStoreMixin):
    def record_recovery_evidence(
        self, draft: RecoveryEvidenceDraft
    ) -> RecoveryEvidenceRecord:
        locks = self.active_semantic_retry_locks(draft.session_id, draft.repo_root)
        if not locks:
            raise RecoveryEvidenceError("no_matching_retry_lock")
        if not materially_different_design(
            draft.previous_design_failure, draft.new_design
        ):
            raise RecoveryEvidenceError("design_not_materially_different")
        scope = self._recovery_scope(draft.session_id, locks)
        if scope.reread_paths != scope.target_paths:
            raise RecoveryEvidenceError("full_read_after_lock_required")
        created_at = int(time())
        record = RecoveryEvidenceRecord(
            target_paths=tuple(scope.target_paths),
            locked_rules=tuple(scope.locked_rules),
            files_reread_after_lock=tuple(scope.reread_paths),
            created_at=created_at,
            schema_version=RECOVERY_EVIDENCE_SCHEMA_VERSION,
        )
        self._persist_recovery(draft, scope, created_at)
        return record

    def _recovery_scope(
        self, session_id: str, locks: dict[str, ObjectDict]
    ) -> _RecoveryScope:
        target_paths = sorted(
            {
                path
                for lock in locks.values()
                if (path := string_value(lock.get(METADATA_PATH))) is not None
            }
        )
        locked_rules = sorted(
            {
                rule
                for lock in locks.values()
                if (rule := string_value(lock.get("rule_id"))) is not None
            }
        )
        minimum_sequence = max(
            (
                sequence
                for lock in locks.values()
                if isinstance((sequence := lock.get("sequence")), int)
            ),
            default=0,
        )
        reread_paths = [
            path
            for path in target_paths
            if (sequence := self.retry_full_read_sequence(session_id, path)) is not None
            and sequence > minimum_sequence
        ]
        return _RecoveryScope(target_paths, locked_rules, reread_paths)

    def _persist_recovery(
        self, draft: RecoveryEvidenceDraft, scope: _RecoveryScope, created_at: int
    ) -> None:
        key = self._recovery_state_key(draft.session_id, draft.repo_root)
        with self._locked_state():
            state = self._load_state()
            state["recovery_evidence"][key] = {
                "target_paths": scope.target_paths,
                "locked_rules": scope.locked_rules,
                "files_reread_after_lock": scope.reread_paths,
                "violated_invariant": draft.violated_invariant,
                "previous_design_failure": draft.previous_design_failure,
                "new_design": draft.new_design,
                "verification": draft.verification,
                "created_at": created_at,
                "schema_version": RECOVERY_EVIDENCE_SCHEMA_VERSION,
            }
            self._save_state(state)

    def use_recovery_evidence(
        self, session_id: str, repo_root: str
    ) -> tuple[bool, str]:
        key = self._recovery_state_key(session_id, repo_root)
        locks = self.active_semantic_retry_locks(session_id, repo_root)
        evidence = object_dict(self._load_state()["recovery_evidence"].get(key))
        status = self._recovery_status(evidence, locks)
        if status != "ready":
            return False, status
        with self._locked_state():
            state = self._load_state()
            _ = state["recovery_evidence"].pop(key, None)
            for raw_key in locks:
                parsed = parse_semantic_key(raw_key)
                _ = state["retry_locks"].pop(raw_key, None)
                _ = state["semantic_deny_hits"].pop(raw_key, None)
                if parsed is not None:
                    self._clear_exact_hits(state, parsed)
            self._save_state(state)
        return True, "consumed"

    def _recovery_status(
        self, evidence: ObjectDict, locks: dict[str, ObjectDict]
    ) -> str:
        base_status = self._base_recovery_status(evidence)
        if base_status != "ready":
            return base_status
        scope = self._recovery_scope_from_locks(locks)
        if object_list(evidence.get("locked_rules")) != scope.locked_rules:
            return "locked_rules_changed"
        if object_list(evidence.get("target_paths")) != scope.target_paths:
            return "targets_changed"
        if object_list(evidence.get("files_reread_after_lock")) != scope.target_paths:
            return "read_proof_missing"
        previous = string_value(evidence.get("previous_design_failure")) or ""
        new = string_value(evidence.get("new_design")) or ""
        return (
            "ready"
            if materially_different_design(previous, new)
            else "design_unchanged"
        )

    def _base_recovery_status(self, evidence: ObjectDict) -> str:
        if not evidence:
            return "missing"
        if evidence.get("schema_version") != RECOVERY_EVIDENCE_SCHEMA_VERSION:
            return "schema_version"
        created_at = evidence.get("created_at")
        if not isinstance(created_at, int):
            return "created_at"
        return "expired" if created_at < int(time()) - self._TTL_SECONDS else "ready"

    @staticmethod
    def _recovery_scope_from_locks(locks: dict[str, ObjectDict]) -> _RecoveryScope:
        rules = sorted(
            {
                rule
                for lock in locks.values()
                if (rule := string_value(lock.get("rule_id"))) is not None
            }
        )
        paths = sorted(
            {
                path
                for lock in locks.values()
                if (path := string_value(lock.get(METADATA_PATH))) is not None
            }
        )
        return _RecoveryScope(paths, rules, paths)

    def _recovery_state_key(self, session_id: str, repo_root: str) -> str:
        identity = {
            SESSION_ID: session_id.strip(),
            "repo_root": self._normalize_path(repo_root),
        }
        return json.dumps(identity, sort_keys=True)
