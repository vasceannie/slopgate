from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from hypothesis import given, settings, strategies

from slopgate.state import (
    HookStateStore,
    SemanticClearRequest,
    SemanticRetryKey,
    SemanticRetryLockPayload,
)
from slopgate.state.retry import RecoveryEvidenceError, RecoveryEvidenceStateMixin
from slopgate.state.retry._identity import (
    materially_different_design,
    parse_semantic_key,
)
from slopgate.state.retry._store import SemanticRetryStoreMixin
from slopgate.state.retry.read_evidence import RetryReadEvidenceMixin


@dataclass(frozen=True, slots=True)
class RecordedPathDenial:
    store: HookStateStore
    key: SemanticRetryKey


IDENTIFIER = strategies.from_regex(r"[a-z][a-z0-9_-]{0,12}", fullmatch=True)


@settings(max_examples=25)
@given(session_id=IDENTIFIER, rule_id=IDENTIFIER, path=IDENTIFIER)
def test_semantic_key_parse_round_trips_json_identity_property(
    session_id: str,
    rule_id: str,
    path: str,
) -> None:
    raw_key = json.dumps(
        {
            "session_id": session_id,
            "repo_root": "/repo",
            "rule_id": rule_id,
            "path": f"src/{path}.py",
            "operation_category": "write",
        },
        sort_keys=True,
    )

    parsed = parse_semantic_key(raw_key)

    assert parsed == SemanticRetryKey(
        session_id=session_id,
        repo_root="/repo",
        rule_id=rule_id,
        path=f"src/{path}.py",
        operation_category="write",
    ), "Semantic retry keys should round-trip through their JSON state identity"


def test_semantic_key_parsing_through_active_lock_lookup(tmp_path: Path) -> None:
    raw_key, key, lock, active_count = _active_lock(tmp_path)

    assert active_count == 1, "active-lock lookup should retain the persisted identity"
    assert parse_semantic_key(raw_key) == key, (
        "Persisted semantic retry keys should parse back to the typed identity"
    )
    assert {
        "rule_id": lock["rule_id"],
        "repo_root": lock["repo_root"],
        "path": lock["path"],
        "operation_category": lock["operation_category"],
        "attempt_fingerprint": lock["attempt_fingerprint"],
        "count": lock["count"],
        "sequence": lock["sequence"],
    } == {
        "rule_id": key.rule_id,
        "repo_root": str(tmp_path.resolve()),
        "path": str((tmp_path / "src/app.py").resolve()),
        "operation_category": None,
        "attempt_fingerprint": "exact",
        "count": 2,
        "sequence": 1,
    }, "active-lock lookup should parse the stored semantic-key fields"


def test_material_design_comparison_rejects_cosmetic_rephrasing() -> None:
    assert not materially_different_design(
        "kept adding positional parameters",
        "KEPT adding positional parameters",
    ), "Cosmetic recovery wording changes should not unlock retries"


def test_recovery_state_public_contract() -> None:
    assert issubclass(HookStateStore, RecoveryEvidenceStateMixin), (
        "HookStateStore should expose recovery evidence behavior"
    )
    assert issubclass(HookStateStore, SemanticRetryStoreMixin), (
        "HookStateStore should expose semantic retry behavior"
    )
    assert issubclass(HookStateStore, RetryReadEvidenceMixin), (
        "HookStateStore should expose retry read evidence behavior"
    )
    assert str(RecoveryEvidenceError("invalid")) == "invalid", (
        "Recovery errors should render stable rejection codes"
    )


def test_semantic_clear_request_clears_resolved_path_denial(tmp_path: Path) -> None:
    recorded = _record_path_denial(tmp_path)

    recorded.store.clear_resolved_semantic_denials(
        SemanticClearRequest(
            session_id=recorded.key.session_id,
            repo_root=recorded.key.repo_root,
            touched_paths=frozenset({recorded.key.path or ""}),
            operation_category="write",
            active_keys=frozenset(),
        )
    )

    assert recorded.store.recent_semantic_failures(recorded.key.session_id) == [], (
        "Clearing a touched path should remove resolved semantic retry failures"
    )


def _record_path_denial(tmp_path: Path) -> RecordedPathDenial:
    store = HookStateStore(tmp_path / "trace")
    key = SemanticRetryKey(
        session_id="integration-session",
        repo_root=str(tmp_path),
        rule_id="PY-CODE-009",
        path=str(tmp_path / "src/app.py"),
        operation_category=None,
    )
    _semantic_count, _exact_count = store.record_semantic_deny(
        key, attempt_fingerprint="exact"
    )
    return RecordedPathDenial(store, key)


def _active_lock(
    tmp_path: Path,
) -> tuple[str, SemanticRetryKey, dict[str, object], int]:
    store = HookStateStore(tmp_path / "trace")
    key = SemanticRetryKey(
        session_id="integration-session",
        repo_root=str(tmp_path),
        rule_id="PY-CODE-009",
        path=str(tmp_path / "src/app.py"),
        operation_category=None,
    )
    store.set_semantic_retry_lock(
        SemanticRetryLockPayload(key=key, attempt_fingerprint="exact", count=2)
    )

    active = store.active_semantic_retry_locks(key.session_id, key.repo_root)
    raw_key, lock = active.popitem()
    return raw_key, key, lock, len(active) + 1
