"""Contract tests for honest, unit-safe recovery analytics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from slopgate._types import ObjectDict, object_dict, object_list
from slopgate.constants import METADATA_DECISION
from slopgate.stats import analyze


@dataclass(frozen=True, slots=True)
class _ResultSpec:
    evaluation_id: str
    event_outcome: str = "blocked_pre_tool"
    findings: tuple[ObjectDict, ...] = ()


def _finding(rule_id: str, decision: str) -> ObjectDict:
    return {
        "rule_id": rule_id,
        METADATA_DECISION: decision,
        "severity": "HIGH",
        "message": f"{rule_id} triggered",
        "metadata": {"path": "src/main.py"},
    }


def _result(spec: _ResultSpec) -> ObjectDict:
    return {
        "timestamp": "2026-07-14T12:00:00+00:00",
        "trace_schema_version": 2,
        "evaluation_id": spec.evaluation_id,
        "operation_id": None,
        "correlation_confidence": "inferred",
        "event_name": "PreToolUse",
        "event_outcome": spec.event_outcome,
        "tool_outcome": "unknown",
        "session_id": "session-1",
        "tool_name": "Edit",
        "candidate_paths": ["src/main.py"],
        "attempt_fingerprint": "fingerprint-1",
        "resolved_repo_root": "/repo",
        "enforcement_mode": "repo_strict",
        "rule_response_version": "1",
        "intervention_tags": [],
        "repair_plan_state": "none",
        "findings": list(spec.findings),
        "errors": [],
    }


DEFAULT_SPEC: Final = _ResultSpec(evaluation_id="evaluation-1")
DENY_SPEC: Final = _ResultSpec(
    evaluation_id="evaluation-1",
    findings=(_finding("PY-CODE-013", "deny"),),
)
MULTI_FINDING_SPEC: Final = _ResultSpec(
    evaluation_id="evaluation-1",
    findings=(
        _finding("PY-CODE-013", "deny"),
        _finding("PY-IMPORT-003", "deny"),
        _finding("GUIDANCE-001", "context"),
    ),
)
CLEAN_SPEC: Final = _ResultSpec(
    evaluation_id="evaluation-1",
    event_outcome="passed_clean",
)


def _analyze_specs(specs: tuple[_ResultSpec, ...]) -> ObjectDict:
    entries = [_result(spec) for spec in specs]
    return object_dict(analyze(entries))


def _counts(stats: ObjectDict, section: str) -> dict[str, int]:
    section_data = object_dict(stats.get(section))
    counts: dict[str, int] = {}
    for item in object_list(section_data.get("counts")):
        pair = object_list(item)
        if len(pair) == 2 and isinstance(pair[0], str) and isinstance(pair[1], int):
            counts[pair[0]] = pair[1]
    return counts


def _legacy_churn_metric_names(stats: ObjectDict) -> set[str]:
    legacy_metrics = object_dict(stats.get("legacy_metrics"))
    legacy_churn = object_dict(legacy_metrics.get("legacy_churn"))
    return set(legacy_churn)


def test_report_contract_has_schema_version() -> None:
    stats = _analyze_specs((DEFAULT_SPEC,))

    assert stats.get("report_schema_version") == 2, "Report schema must be versioned"


def test_report_contract_marks_legacy_metrics_deprecated() -> None:
    stats = _analyze_specs((DEFAULT_SPEC,))
    legacy_metrics = object_dict(stats.get("legacy_metrics"))

    assert legacy_metrics.get("status") == "deprecated", (
        "Legacy metrics must carry an explicit deprecated status"
    )


def test_legacy_churn_uses_honest_metric_names() -> None:
    stats = _analyze_specs((DENY_SPEC,))

    assert _legacy_churn_metric_names(stats) == {
        "single_occurrence_deny_key_ratio",
        "median_extra_denials_per_repeated_key",
        "repeated_deny_key_count_by_rule",
        "session_rule_denial_frequency",
        "top_looping_files",
        "top_pathless_loop_rules",
    }, "Legacy churn must expose only names that describe denial frequency"


def test_report_contract_removes_obsolete_outcome_names() -> None:
    stats = _analyze_specs((DEFAULT_SPEC,))
    obsolete_names = {
        "first_time_resolution_rate",
        "median_retries_before_resolution",
        "repeated_deny_rate_by_rule",
    }

    assert set(stats).isdisjoint(obsolete_names), (
        "Report must not expose outcome-sounding legacy metric names"
    )


def test_event_outcomes_use_result_event_denominator() -> None:
    stats = _analyze_specs((MULTI_FINDING_SPEC,))
    event_outcomes = object_dict(stats.get("event_outcomes"))

    assert event_outcomes.get("total") == 1, "One result must be one outcome event"


def test_event_outcomes_count_one_result_once() -> None:
    stats = _analyze_specs((MULTI_FINDING_SPEC,))

    assert _counts(stats, "event_outcomes") == {"blocked_pre_tool": 1}, (
        "Event outcomes must count result events"
    )


def test_finding_decisions_use_finding_denominator() -> None:
    stats = _analyze_specs((MULTI_FINDING_SPEC,))
    finding_decisions = object_dict(stats.get("finding_decisions"))

    assert finding_decisions.get("total") == 3, (
        "Finding denominator must count findings independently"
    )


def test_finding_decisions_count_each_finding() -> None:
    stats = _analyze_specs((MULTI_FINDING_SPEC,))

    assert _counts(stats, "finding_decisions") == {"deny": 2, "context": 1}, (
        "Finding decisions must not be divided by event count"
    )


def test_clean_result_has_passed_clean_event_outcome() -> None:
    stats = _analyze_specs((CLEAN_SPEC,))

    assert _counts(stats, "event_outcomes") == {"passed_clean": 1}, (
        "Clean results must be represented as event outcomes"
    )


def test_clean_result_has_zero_finding_denominator() -> None:
    stats = _analyze_specs((CLEAN_SPEC,))
    finding_decisions = object_dict(stats.get("finding_decisions"))

    assert finding_decisions.get("total") == 0, (
        "A clean event must not create a synthetic finding"
    )


def test_clean_result_has_empty_finding_distribution() -> None:
    stats = _analyze_specs((CLEAN_SPEC,))

    assert _counts(stats, "finding_decisions") == {}, (
        "A clean event must leave the finding distribution empty"
    )


def test_duplicate_evaluation_ids_are_counted_once() -> None:
    stats = _analyze_specs((DENY_SPEC, DENY_SPEC))

    assert stats.get("analyzed_events") == 1, (
        "Duplicate evaluations must not double-count events"
    )


def test_duplicate_evaluation_ids_are_reported_in_coverage() -> None:
    stats = _analyze_specs((DENY_SPEC, DENY_SPEC))
    coverage = object_dict(stats.get("telemetry_coverage"))

    assert coverage.get("duplicate_records_removed") == 1, (
        "Deduplication must remain visible in telemetry coverage"
    )


def test_legacy_record_without_explicit_outcome_remains_unknown() -> None:
    entry = _result(DENY_SPEC)
    del entry["trace_schema_version"]
    del entry["evaluation_id"]
    del entry["event_outcome"]

    stats = object_dict(analyze([entry]))

    assert _counts(stats, "event_outcomes") == {"unknown": 1}, (
        "Legacy findings must not fabricate an observed event outcome"
    )
