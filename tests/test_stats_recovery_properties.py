"""Property checks for recovery sequence aggregation invariants."""

from __future__ import annotations

from typing import Final

import pytest
from hypothesis import given, settings, strategies

from slopgate._types import ObjectDict, object_dict
from slopgate.constants import METADATA_DECISION, POST_TOOL_USE, PRE_TOOL_USE, STOP
from slopgate.stats.recovery.chains import build_chains
from slopgate.stats.recovery.normalization import normalize_entries
from slopgate.stats.recovery.rule_metrics import recovery_report

_EVENT_NAMES: Final = {
    "deny": PRE_TOOL_USE,
    "retry": PRE_TOOL_USE,
    "success": POST_TOOL_USE,
    "stop": STOP,
}
_EVENT_OUTCOMES: Final = {
    "deny": "blocked_pre_tool",
    "retry": "passed_clean",
    "success": "passed_clean",
    "stop": "passed_clean",
}
_TOOL_OUTCOMES: Final = {
    "deny": "unknown",
    "retry": "unknown",
    "success": "success",
    "stop": "unknown",
}
_DENIAL_FINDING: Final = {
    "rule_id": "RULE-001",
    METADATA_DECISION: "deny",
    "severity": "HIGH",
    "message": "RULE-001 triggered",
    "metadata": {"path": "src/app.py"},
}


def _event(index: int, kind: str) -> ObjectDict:
    is_terminal = kind == "stop"
    return {
        "timestamp": f"2026-07-14T12:00:{index:02d}+00:00",
        "trace_schema_version": 2,
        "evaluation_id": f"event-{index}",
        "correlation_confidence": "inferred",
        "event_name": _EVENT_NAMES[kind],
        "event_outcome": _EVENT_OUTCOMES[kind],
        "tool_outcome": _TOOL_OUTCOMES[kind],
        "session_id": "session-1",
        "tool_name": "Edit",
        "candidate_paths": [] if is_terminal else ["src/app.py"],
        "attempt_fingerprint": None if is_terminal else kind,
        "resolved_repo_root": "/repo",
        "enforcement_mode": "repo_strict",
        "platform_capability": "full",
        "rule_response_version": "1",
        "intervention_tags": [],
        "repair_plan_state": "none",
        "findings": [_DENIAL_FINDING] if kind == "deny" else [],
        "errors": [],
    }


_SEQUENCES = strategies.lists(
    strategies.sampled_from(tuple(_EVENT_NAMES)),
    max_size=20,
)
_RATE_NAMES: Final = (
    "first_retry_rule_clearance",
    "first_retry_operation_success",
    "unchanged_first_retry",
    "changed_first_retry",
)


def _recovery_analysis(kinds: list[str]) -> tuple[ObjectDict, int]:
    batch = normalize_entries([_event(index, kind) for index, kind in enumerate(kinds)])
    report = recovery_report(batch.events, batch.duplicate_records_removed)
    chain_count = len(build_chains(batch.events))
    return report, chain_count


@given(_SEQUENCES)
@settings(max_examples=50)
def test_recovery_partitions_always_cover_every_chain(kinds: list[str]) -> None:
    report, chain_count = _recovery_analysis(kinds)
    summary = object_dict(report.get("summary"))
    partition_values = tuple(
        summary.get(key) for key in ("recovered", "abandoned", "open_censored")
    )
    partition_total = sum(value for value in partition_values if isinstance(value, int))

    assert partition_total == chain_count, (
        "Recovery states must form an exact partition of all chains"
    )


@pytest.mark.parametrize("rate_name", _RATE_NAMES)
@given(kinds=_SEQUENCES)
@settings(max_examples=50)
def test_recovery_percentages_are_bounded_or_unavailable(
    kinds: list[str], rate_name: str
) -> None:
    report, _chain_count = _recovery_analysis(kinds)
    rates = object_dict(report["rates"])
    percentage = object_dict(rates[rate_name])["percentage"]

    assert (
        percentage is None
        or isinstance(percentage, (int, float))
        and 0 <= percentage <= 100
    ), "Recovery percentages must remain unavailable or within 0–100"
