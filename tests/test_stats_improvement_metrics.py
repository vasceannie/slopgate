"""Focused contracts for reusable improvement metric primitives."""

from __future__ import annotations

import json
from pathlib import Path

from hypothesis import given, strategies

from slopgate._types import object_dict, object_list
from slopgate.stats.improvement import (
    ResultRecord,
    evaluate_episodes,
    parse_result_records,
)
from slopgate.stats.improvement.metrics import comparison_snapshot_metrics


def _fixture_records() -> list[ResultRecord]:
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "improvement"
        / "write_block_clean_edit_resolved.json"
    )
    fixture = object_dict(json.loads(fixture_path.read_text(encoding="utf-8")))
    return parse_result_records(object_list(fixture.get("entries")))


@given(repetitions=strategies.integers(min_value=1, max_value=5))
def test_comparison_snapshot_metrics_use_explicit_evaluation_scope(
    repetitions: int,
) -> None:
    records = _fixture_records() * repetitions
    evaluation = evaluate_episodes(records)

    window, runtime, evaluation_p95 = comparison_snapshot_metrics(
        records, evaluation
    )

    assert window["first_attempt_clean_rate"] == {
        "rate": 0.0,
        "numerator": 0,
        "denominator": 1,
    }, "comparison windows must use the supplied first-observed records"
    assert runtime["evaluation_ms"] == {"p50": 10.0, "p95": 10.0}, (
        "comparison snapshots must report evaluation timing percentiles"
    )
    assert evaluation_p95 == 10.0, (
        "comparison snapshots must report the evaluation p95 scalar"
    )
