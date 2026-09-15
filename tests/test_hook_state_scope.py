from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.state import (
    HookStateCorruptionError,
    HookStateStore,
    RepairRequiredPayload,
    RepairTarget,
    RetryLockPayload,
)


def test_hook_state_store_shares_same_worktree_scope(tmp_path: Path) -> None:
    first_worktree = HookStateStore(tmp_path, scope="/repo/first", path_base=tmp_path)
    same_worktree = HookStateStore(tmp_path, scope="/repo/first", path_base=tmp_path)

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
        "paths": [str((tmp_path / "src/app.py").resolve())],
        "attempt_fingerprint": "attempt-1",
        "count": 2,
    }


def test_hook_state_store_isolates_different_worktree_scopes(tmp_path: Path) -> None:
    first_worktree = HookStateStore(tmp_path, scope="/repo/first", path_base=tmp_path)
    other_worktree = HookStateStore(tmp_path, scope="/repo/other", path_base=tmp_path)

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
    canonical = HookStateStore(tmp_path, scope="/repo/first", path_base=tmp_path)
    equivalent = HookStateStore(
        tmp_path, scope="/repo/other/../first", path_base=tmp_path
    )
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
        "paths": [str((tmp_path / "src/app.py").resolve())],
        "attempt_fingerprint": "attempt-1",
        "count": 2,
    }, "equivalent worktree paths must preserve the exact shared state"


def _repair_store(tmp_path: Path) -> tuple[HookStateStore, HookStateStore, str]:
    first_worktree = HookStateStore(tmp_path, scope="/repo/first", path_base=tmp_path)
    same_worktree = HookStateStore(tmp_path, scope="/repo/first", path_base=tmp_path)
    target = RepairTarget("QUALITY-LINT-001", "src/app.py", "src/app.py", None, None)
    generation = first_worktree.repair_generation(targets=[target])

    first_worktree.mark_repair_required(
        generation,
        RepairRequiredPayload(
            session_id="session-one",
            call_id="call-one",
            worktree=first_worktree.scope,
            targets=[target],
        ),
    )

    return first_worktree, same_worktree, generation


def test_repair_required_state_is_shared(tmp_path: Path) -> None:
    _first_worktree, same_worktree, generation = _repair_store(tmp_path)
    required = same_worktree.get_repair_required()
    assert required is not None
    assert {
        key: required[key]
        for key in (
            "status",
            "generation",
            "session_id",
            "call_id",
            "worktree",
            "rule_ids",
            "paths",
            "targets",
        )
    } == {
        "status": "REPAIR_REQUIRED",
        "generation": generation,
        "session_id": "session-one",
        "call_id": "call-one",
        "worktree": "/repo/first",
        "rule_ids": ["QUALITY-LINT-001"],
        "paths": [str((tmp_path / "src/app.py").resolve())],
        "targets": [
            {
                "rule_id": "QUALITY-LINT-001",
                "path": str((tmp_path / "src/app.py").resolve()),
                "raw_path": "src/app.py",
                "function": None,
                "error": None,
            }
        ],
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
    store = HookStateStore(tmp_path, scope="/repo/first", path_base=tmp_path)
    target = RepairTarget("QUALITY-LINT-001", "src/app.py", "src/app.py", None, None)
    stale_generation = store.repair_generation(
        targets=[target], event_identity="session-one\ncall-one"
    )
    current_generation = store.repair_generation(
        targets=[target], event_identity="session-one\ncall-two"
    )

    assert stale_generation != current_generation, (
        "distinct repair occurrences must produce distinct CAS generations"
    )


def test_repair_generation_is_independent_of_process_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "event-repo"
    store = HookStateStore(tmp_path, scope=str(repo), path_base=repo)
    target = RepairTarget("QUALITY-LINT-001", "src/app.py", "src/app.py", None, None)

    monkeypatch.chdir(tmp_path)
    first = store.repair_generation(targets=[target])
    monkeypatch.chdir(tmp_path.parent)
    second = store.repair_generation(targets=[target])

    assert first == second, "generation identity must not depend on daemon cwd"


def test_corrupt_hook_state_fails_closed(tmp_path: Path) -> None:
    store, _same_worktree, _generation = _repair_store(tmp_path)
    state_file = next(tmp_path.glob("hook-state-*.json"))
    state_file.write_text("{not-json", encoding="utf-8")

    with pytest.raises(HookStateCorruptionError):
        store.get_repair_required()
