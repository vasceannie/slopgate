from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from slopgate.failure_profile import (
    FailureProfileDimension,
    FailureProfileEntry,
    FailureProfileSnapshot,
    FailureProfileStore,
    FailureRisk,
)
from slopgate.models import FailureProfileConfig
from tests.failure_profile.support import seed_blocked_risks


TODAY = date(2026, 7, 15)


def _decay_store(tmp_path: Path) -> FailureProfileStore:
    store = FailureProfileStore(
        tmp_path / "trace",
        tmp_path / "repo",
        FailureProfileConfig(enabled=True, retention_days=30, max_entries=8),
    )
    store.record(
        FailureProfileDimension(
            rule_id="RULE-A",
            path_role="source",
            language="python",
            platform="claude",
            model_identifier="gpt-5.6-sol",
            resolution_outcome="blocked",
        ),
        today=TODAY,
        count=4,
    )
    return store


def test_profile_decay_uses_rolling_retention(
    tmp_path: Path,
) -> None:
    store = _decay_store(tmp_path)

    midpoint = store.snapshot(today=TODAY + timedelta(days=15))

    assert isinstance(midpoint, FailureProfileSnapshot), (
        "Snapshot should use the public value type"
    )
    assert isinstance(midpoint.entries[0], FailureProfileEntry), (
        "Snapshot entries should use the public value type"
    )
    assert midpoint.entries[0].decayed_count == 2.0, (
        "Half the retention window should halve the aggregate count"
    )


def test_profile_prunes_at_retention_boundary(tmp_path: Path) -> None:
    store = _decay_store(tmp_path)

    expired = store.snapshot(today=TODAY + timedelta(days=30))

    assert expired.entries == (), "Entries at the retention boundary should be pruned"


def test_profile_cap_is_deterministic_for_equal_scores(tmp_path: Path) -> None:
    store = FailureProfileStore(
        tmp_path / "trace",
        tmp_path / "repo",
        FailureProfileConfig(enabled=True, retention_days=30, max_entries=2),
    )
    for rule_id in ("RULE-C", "RULE-A", "RULE-B"):
        store.record(
            FailureProfileDimension(
                rule_id=rule_id,
                path_role="source",
                language="python",
                platform="claude",
                model_identifier="gpt-5.6-sol",
                resolution_outcome="blocked",
            ),
            today=TODAY,
        )

    snapshot = store.snapshot(today=TODAY)

    assert [entry.dimension.rule_id for entry in snapshot.entries] == [
        "RULE-A",
        "RULE-B",
    ], "Equal-score cap ties should use stable dimension ordering"


def test_top_risks_returns_only_three_to_five_recurring_blocked_dimensions(
    tmp_path: Path,
) -> None:
    store = FailureProfileStore(
        tmp_path / "trace",
        tmp_path / "repo",
        FailureProfileConfig(enabled=True, retention_days=30, max_entries=8),
    )
    seed_blocked_risks(store, TODAY)
    store.record(
        FailureProfileDimension(
            rule_id="RULE-RESOLVED",
            path_role="source",
            language="python",
            platform="claude",
            model_identifier="gpt-5.6-sol",
            resolution_outcome="resolved",
        ),
        today=TODAY,
        count=20,
    )

    risks = store.top_risks(today=TODAY)

    assert all(isinstance(risk, FailureRisk) for risk in risks), (
        "Ranked risks should use the public value type"
    )
    assert len(risks) == 5, "Guidance should include at most five recurring risks"
    assert [risk.rule_id for risk in risks] == [
        "RULE-5",
        "RULE-4",
        "RULE-3",
        "RULE-2",
        "RULE-1",
    ], "Guidance should rank recurring blocked risks by decayed count"


def test_top_risks_waits_for_three_recurring_dimensions(tmp_path: Path) -> None:
    store = FailureProfileStore(
        tmp_path / "trace",
        tmp_path / "repo",
        FailureProfileConfig(enabled=True, retention_days=30, max_entries=8),
    )
    for rule_id in ("RULE-A", "RULE-B"):
        store.record(
            FailureProfileDimension(
                rule_id=rule_id,
                path_role="source",
                language="python",
                platform="claude",
                model_identifier=None,
                resolution_outcome="blocked",
            ),
            today=TODAY,
            count=2,
        )

    assert store.top_risks(today=TODAY) == (), (
        "First-write guidance should inject either three to five risks or none"
    )
