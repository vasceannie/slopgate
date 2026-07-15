"""Behavior tests for typed result-record normalization."""

from __future__ import annotations

from hypothesis import given, strategies

from slopgate._types import ObjectDict
from slopgate.constants import METADATA_DECISION
from slopgate.stats.recovery import (
    NormalizationResult,
    NormalizedEvent,
    NormalizedFinding,
    normalize_entries,
)
from slopgate.stats.recovery.dedupe import dedupe_entries
from slopgate.stats.recovery.legacy import legacy_churn
from slopgate.stats.recovery.records import (
    CorrelationConfidence,
    EventOutcome,
    FindingDecision,
    RecoveryTarget,
    RepairPlanState,
    TargetType,
    ToolOutcome,
)


def _result_entry() -> ObjectDict:
    return {
        "timestamp": "2026-07-14T12:00:00+00:00",
        "trace_schema_version": 2,
        "evaluation_id": "evaluation-1",
        "operation_id": None,
        "correlation_confidence": "inferred",
        "event_name": "PreToolUse",
        "event_outcome": "blocked_pre_tool",
        "tool_outcome": "unknown",
        "session_id": "session-1",
        "tool_name": "Edit",
        "candidate_paths": ["src/main.py"],
        "attempt_fingerprint": "fingerprint-1",
        "resolved_repo_root": "/repo",
        "enforcement_mode": "repo_strict",
        "platform_capability": "full",
        "rule_response_version": "1",
        "intervention_tags": ["skill-guidance-emitted"],
        "repair_plan_state": "requested",
        "findings": [
            {
                "rule_id": "PY-CODE-013",
                METADATA_DECISION: "deny",
                "severity": "HIGH",
                "message": "Thin wrapper",
                "metadata": {"path": "src/main.py"},
            }
        ],
        "errors": [],
    }


def _entries_from_tokens(tokens: list[str]) -> list[ObjectDict]:
    entries: list[ObjectDict] = []
    for index, token in enumerate(tokens):
        entry = _result_entry()
        if token == "fixture":
            entry["evaluation_id"] = f"fixture-evaluation-{index}"
            entry["session_id"] = f"fixture-session-{index}"
        else:
            entry["evaluation_id"] = token
        entries.append(entry)
    return entries


def _normalized_evidence(batch: NormalizationResult) -> ObjectDict:
    event: NormalizedEvent = batch.events[0]
    finding: NormalizedFinding = event.findings[0]
    target: RecoveryTarget = finding.targets[0]
    event_outcome: EventOutcome = event.event_outcome
    decision: FindingDecision = finding.decision
    correlation: CorrelationConfidence = event.correlation_confidence
    tool_outcome: ToolOutcome = event.tool_outcome
    repair_state: RepairPlanState = event.repair_plan_state
    target_type: TargetType = target.target_type
    return {
        "event_count": len(batch.events),
        "duplicates": batch.duplicate_records_removed,
        "schema_versions": batch.trace_schema_versions_seen,
        "evaluation_id": event.evaluation_id,
        "event_outcome": event_outcome.value,
        METADATA_DECISION: decision.value,
        "correlation": correlation.value,
        "tool_outcome": tool_outcome.value,
        "repair_state": repair_state.value,
        "target_type": target_type.value,
        "target": target.value,
    }


def test_normalize_entries_deduplicates_and_preserves_typed_evidence() -> None:
    entry = _result_entry()

    batch: NormalizationResult = normalize_entries([entry, entry])

    assert _normalized_evidence(batch) == {
        "event_count": 1,
        "duplicates": 1,
        "schema_versions": (2,),
        "evaluation_id": "evaluation-1",
        "event_outcome": "blocked_pre_tool",
        METADATA_DECISION: "deny",
        "correlation": "inferred",
        "tool_outcome": "unknown",
        "repair_state": "requested",
        "target_type": "file",
        "target": "src/main.py",
    }, "Normalization must preserve typed recovery evidence without duplicates"


def test_dedupe_entries_preserves_first_source_record() -> None:
    first = _result_entry()
    duplicate = _result_entry()
    unkeyed = _result_entry()
    del unkeyed["evaluation_id"]

    result = dedupe_entries([first, duplicate, unkeyed])
    retained_indexes = tuple(index for index, _entry in result.entries)

    assert (retained_indexes, result.duplicate_records_removed) == ((0, 2), 1), (
        "Deduplication must keep the first evaluation and every unkeyed record"
    )


def test_quality_lint_collectors_become_separate_rule_variants() -> None:
    entry = _result_entry()
    entry["findings"] = [
        {
            "rule_id": "QUALITY-LINT-001",
            METADATA_DECISION: "block",
            "severity": "HIGH",
            "message": "Quality gate failed",
            "metadata": {"failing_collectors": ["long-method", "duplicate-code"]},
        }
    ]

    batch = normalize_entries([entry])
    variants = tuple(finding.rule_variant for finding in batch.events[0].findings)

    assert variants == ("long-method", "duplicate-code"), (
        "Each failing collector must retain its own recovery-chain variant"
    )


def test_finding_path_precedes_broader_candidate_paths() -> None:
    entry = _result_entry()
    entry["candidate_paths"] = ["src/main.py", "src/other.py"]

    targets = normalize_entries([entry]).events[0].findings[0].targets

    assert targets == (RecoveryTarget(TargetType.FILE, "src/main.py"),), (
        "A finding-specific path must not fan out into unrelated candidate paths"
    )


def test_legacy_record_is_marked_without_fabricating_schema_coverage() -> None:
    entry = _result_entry()
    del entry["trace_schema_version"]
    del entry["evaluation_id"]

    batch = normalize_entries([entry])
    event = batch.events[0]

    assert (event.is_legacy, batch.trace_schema_versions_seen) == (True, ()), (
        "Legacy records must be explicit and must not claim v2 schema coverage"
    )


@given(
    strategies.lists(
        strategies.sampled_from(["evaluation-a", "evaluation-b", "fixture"]),
        max_size=12,
    )
)
def test_normalize_entries_partitions_every_raw_record(tokens: list[str]) -> None:
    entries = _entries_from_tokens(tokens)

    batch = normalize_entries(entries)
    accounted_records = (
        len(batch.events) + batch.fixture_filtered + batch.duplicate_records_removed
    )

    assert accounted_records == batch.raw_total_events, (
        "Normalization must account for every retained, filtered, or duplicate record"
    )


@given(
    strategies.lists(
        strategies.sampled_from(["evaluation-a", "evaluation-b", "fixture"]),
        max_size=12,
    )
)
def test_legacy_churn_single_occurrence_ratio_is_bounded(tokens: list[str]) -> None:
    batch = normalize_entries(_entries_from_tokens(tokens))

    ratio = legacy_churn(batch.events).get("single_occurrence_deny_key_ratio")

    assert ratio is None or isinstance(ratio, float) and 0.0 <= ratio <= 1.0, (
        "Legacy churn ratios must be unavailable or bounded probabilities"
    )
