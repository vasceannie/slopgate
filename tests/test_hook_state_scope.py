from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.state import (
    HookStateCorruptionError,
    HookStateStore,
    RepairRequiredPayload,
    RetryLockPayload,
)


def test_hook_state_store_shares_same_worktree_scope(tmp_path: Path) -> None:
    first_worktree = HookStateStore(tmp_path, scope="/repo/first")
    same_worktree = HookStateStore(tmp_path, scope="/repo/first")

    first_worktree.set_retry_lock(
        "session-one",
        payload=RetryLockPayload(
            repeated_rule_ids=["QUALITY-LINT-001"],
            current_rule_ids=["QUALITY-LINT-001"],
            paths=["src/app.py"],
            attempt_fingerprint="attempt-1",
            count=2,
        ),
    )

    assert same_worktree.get_retry_lock("session-one") == {
        "repeated_rule_ids": ["QUALITY-LINT-001"],
        "current_rule_ids": ["QUALITY-LINT-001"],
        "paths": [str(Path("src/app.py").resolve())],
        "attempt_fingerprint": "attempt-1",
        "count": 2,
    }


def test_hook_state_store_isolates_different_worktree_scopes(tmp_path: Path) -> None:
    first_worktree = HookStateStore(tmp_path, scope="/repo/first")
    other_worktree = HookStateStore(tmp_path, scope="/repo/other")

    first_worktree.set_retry_lock(
        "session-one",
        payload=RetryLockPayload(
            repeated_rule_ids=["QUALITY-LINT-001"],
            current_rule_ids=["QUALITY-LINT-001"],
            paths=["src/app.py"],
            attempt_fingerprint="attempt-1",
            count=2,
        ),
    )

    assert other_worktree.get_retry_lock("session-one") is None


def test_hook_state_store_canonicalizes_equivalent_worktree_scopes(
    tmp_path: Path,
) -> None:
    canonical = HookStateStore(tmp_path, scope="/repo/first")
    equivalent = HookStateStore(tmp_path, scope="/repo/other/../first")
    canonical.set_retry_lock(
        "session-one",
        payload=RetryLockPayload(
            repeated_rule_ids=["QUALITY-LINT-001"],
            current_rule_ids=["QUALITY-LINT-001"],
            paths=["src/app.py"],
            attempt_fingerprint="attempt-1",
            count=2,
        ),
    )

    assert equivalent.get_retry_lock("session-one") == {
        "repeated_rule_ids": ["QUALITY-LINT-001"],
        "current_rule_ids": ["QUALITY-LINT-001"],
        "paths": [str(Path("src/app.py").resolve())],
        "attempt_fingerprint": "attempt-1",
        "count": 2,
    }, "equivalent worktree paths must preserve the exact shared state"


def _repair_store(tmp_path: Path) -> tuple[HookStateStore, HookStateStore, str]:
    first_worktree = HookStateStore(tmp_path, scope="/repo/first")
    same_worktree = HookStateStore(tmp_path, scope="/repo/first")
    generation = first_worktree.repair_generation(
        rule_ids=["QUALITY-LINT-001"], paths=["src/app.py"]
    )

    first_worktree.mark_repair_required(
        generation,
        RepairRequiredPayload(
            session_id="session-one",
            call_id="call-one",
            rule_ids=["QUALITY-LINT-001"],
            paths=["src/app.py"],
        ),
    )

    return first_worktree, same_worktree, generation


def test_repair_required_state_is_shared(tmp_path: Path) -> None:
    _first_worktree, same_worktree, generation = _repair_store(tmp_path)
    required = same_worktree.get_repair_required()
    assert required is not None
    assert {
        key: required[key]
        for key in ("status", "generation", "session_id", "call_id", "rule_ids", "paths")
    } == {
        "status": "REPAIR_REQUIRED",
        "generation": generation,
        "session_id": "session-one",
        "call_id": "call-one",
        "rule_ids": ["QUALITY-LINT-001"],
        "paths": [str(Path("src/app.py").resolve())],
    }, "Shared worktree state should preserve repair provenance"
    assert required["status"] == "REPAIR_REQUIRED", "Repair state should be pending"


def test_repair_required_state_requires_matching_generation(tmp_path: Path) -> None:
    first_worktree, same_worktree, generation = _repair_store(tmp_path)
    assert same_worktree.clear_repair_required("wrong-generation") is False, (
        "A stale generation must not clear pending repair state"
    )
    assert same_worktree.clear_repair_required(generation) is True, (
        "The matching generation should clear pending repair state"
    )
    assert first_worktree.get_repair_required() is None, (
        "Clearing through one scoped store should be visible to its peers"
    )


def test_repair_generation_distinguishes_event_occurrences(tmp_path: Path) -> None:
    store = HookStateStore(tmp_path, scope="/repo/first")
    stale_generation = store.repair_generation(
        rule_ids=["QUALITY-LINT-001"],
        paths=["src/app.py"],
        event_identity="session-one\ncall-one",
    )
    current_generation = store.repair_generation(
        rule_ids=["QUALITY-LINT-001"],
        paths=["src/app.py"],
        event_identity="session-one\ncall-two",
    )

    assert stale_generation != current_generation, (
        "distinct repair occurrences must produce distinct CAS generations"
    )


def test_corrupt_hook_state_fails_closed(tmp_path: Path) -> None:
    store = HookStateStore(tmp_path, scope="/repo/first")
    store.mark_repair_required(
        "generation-one",
        RepairRequiredPayload(
            session_id="session-one",
            call_id="call-one",
            rule_ids=["QUALITY-LINT-001"],
            paths=["src/app.py"],
        ),
    )
    state_files = tuple(tmp_path.glob("hook-state-*.json"))
    assert len(state_files) == 1, "the scoped store should own one state file"
    state_files[0].write_text("{not-json", encoding="utf-8")

    with pytest.raises(HookStateCorruptionError):
        store.get_repair_required()
