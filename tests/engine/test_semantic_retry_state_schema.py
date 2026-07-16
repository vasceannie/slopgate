from __future__ import annotations

import json
from pathlib import Path
from time import time

from slopgate._types import object_dict
from slopgate.state import SemanticRetryKey
from tests.test_hook_state_spec import InspectableHookStateStore


def test_legacy_state_load_adds_semantic_sections_without_dropping_exact_hits(
    tmp_path: Path,
) -> None:
    store = InspectableHookStateStore(tmp_path)
    exact_key = json.dumps(
        {
            "session_id": "legacy-session",
            "rule_id": "PY-CODE-013",
            "path": str((tmp_path / "legacy.py").resolve()),
            "attempt_fingerprint": "legacy-fingerprint",
        },
        sort_keys=True,
    )
    store.save_state_for_test(
        {
            "deny_hits": {exact_key: 2},
            "retry_locks": {},
            "repair_plans": {"legacy-session": {"timestamp": int(time())}},
        }
    )

    state = store.load_state_for_test()

    assert state["deny_hits"] == {exact_key: 2}, (
        "Additive schema migration must preserve exact diagnostic counters"
    )
    assert state["semantic_deny_hits"] == {}, (
        "Legacy state should deterministically initialize semantic counters"
    )
    assert state["recovery_evidence"] == {}, (
        "Legacy prompt repair plans must not migrate into structured evidence"
    )
    assert state["full_read_events"] == {}, (
        "Legacy state should initialize ordered read evidence"
    )
    assert state["event_sequence"] == 0, (
        "Legacy state should initialize the deterministic event sequence"
    )


def test_semantic_counter_pruning_is_bounded_and_keeps_current_identity(
    tmp_path: Path,
) -> None:
    store = InspectableHookStateStore(tmp_path)
    _seed_semantic_entries(store, tmp_path)
    protected = SemanticRetryKey(
        session_id="session-a",
        repo_root=str(tmp_path),
        rule_id="RULE-PROTECTED",
        path=str(tmp_path / "protected.py"),
        operation_category=None,
    )

    count, _exact_count = store.record_semantic_deny(protected, "exact")
    state = store.load_state_for_test()
    semantic = object_dict(state["semantic_deny_hits"])

    assert count == 1, "The newly protected semantic identity should start at one"
    assert len(semantic) == 512, (
        "Semantic counter state should remain deterministically bounded"
    )
    assert store.semantic_state_key(protected) in semantic, (
        "Pruning must retain the currently updated semantic identity"
    )


def _seed_semantic_entries(store: InspectableHookStateStore, root: Path) -> None:
    now = int(time())
    entries = {
        json.dumps(
            {
                "session_id": "session-a",
                "repo_root": str(root.resolve()),
                "rule_id": f"RULE-{index:03d}",
                "path": str((root / f"module_{index}.py").resolve()),
                "operation_category": None,
            },
            sort_keys=True,
        ): {"count": index % 4, "timestamp": now}
        for index in range(520)
    }
    store.save_state_for_test({"semantic_deny_hits": entries})
