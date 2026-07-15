"""Unit-safe report metrics over normalized completed results."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Final

from slopgate._types import ObjectDict
from slopgate.constants import METADATA_PATH, STOP, STATS_TOP_RULE_LIMIT, UNKNOWN_VALUE

from .chains import recovery_rate
from .legacy import legacy_churn
from .normalization import normalize_entries
from .rule_metrics import recovery_report
from .scopes import RecoveryScope, scoped_events
from .records import (
    CorrelationConfidence,
    FindingDecision,
    NormalizationResult,
    NormalizedEvent,
    TargetType,
    ToolOutcome,
)

REPORT_SCHEMA_VERSION: Final = 2
_TERMINAL_EVENTS: Final = frozenset(
    {STOP, "SubagentStop", "SessionEnd", "TaskCompleted"}
)


@dataclass(slots=True)
class _Counters:
    """Mutable single-pass accumulators for report summary data."""

    by_event: Counter[str] = field(default_factory=Counter)
    event_outcomes: Counter[str] = field(default_factory=Counter)
    finding_decisions: Counter[str] = field(default_factory=Counter)
    by_severity: Counter[str] = field(default_factory=Counter)
    enforcement_rules: Counter[str] = field(default_factory=Counter)
    advisory_rules: Counter[str] = field(default_factory=Counter)
    enrichment_rules: Counter[str] = field(default_factory=Counter)
    by_tool: Counter[str] = field(default_factory=Counter)
    by_session: Counter[str] = field(default_factory=Counter)
    denied_files: Counter[str] = field(default_factory=Counter)
    daily_counts: Counter[str] = field(default_factory=Counter)
    rule_examples: dict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )


def _accumulate_result(event: NormalizedEvent, counters: _Counters) -> None:
    counters.by_event[event.event_name] += 1
    counters.event_outcomes[event.event_outcome.value] += 1
    counters.by_tool[event.tool_name] += 1
    counters.by_session[event.session_id] += 1
    if event.timestamp:
        counters.daily_counts[event.timestamp[:10]] += 1
    for finding in event.distinct_findings():
        label = finding.label
        counters.finding_decisions[finding.decision.value] += 1
        counters.by_severity[finding.severity] += 1
        if finding.rule_id == "ENRICHMENT" or finding.rule_id.startswith("_ENRICHMENT"):
            counters.enrichment_rules[label] += 1
        if finding.is_blocking:
            counters.enforcement_rules[label] += 1
            for target in finding.targets:
                if target.target_type is TargetType.FILE:
                    counters.denied_files[target.value] += 1
            if len(counters.rule_examples[label]) < 3:
                counters.rule_examples[label].append(finding.message)
        elif finding.decision in {
            FindingDecision.ASK,
            FindingDecision.WARN,
            FindingDecision.CONTEXT,
            FindingDecision.INFO,
        }:
            counters.advisory_rules[label] += 1


def _distribution(counter: Counter[str], total: int) -> ObjectDict:
    return {
        "total": total,
        "counts": counter.most_common(),
        "rates": {
            label: recovery_rate(count, total) for label, count in counter.most_common()
        },
    }


def _coverage(batch: NormalizationResult) -> ObjectDict:
    events = batch.events
    total = len(events)
    post_tool_events = [event for event in events if event.event_name == "PostToolUse"]
    correlation_counts = Counter(event.correlation_confidence.value for event in events)
    return {
        METADATA_PATH: recovery_rate(
            sum(bool(event.candidate_paths) for event in events), total
        ),
        "attempt_fingerprint": recovery_rate(
            sum(event.attempt_fingerprint is not None for event in events),
            total,
        ),
        "exact_operation_id": recovery_rate(
            sum(
                event.correlation_confidence is CorrelationConfidence.EXACT
                for event in events
            ),
            total,
        ),
        "post_tool_outcome": recovery_rate(
            sum(
                event.tool_outcome is not ToolOutcome.UNKNOWN
                for event in post_tool_events
            ),
            len(post_tool_events),
        ),
        "explicit_terminal_event": recovery_rate(
            sum(event.event_name in _TERMINAL_EVENTS for event in events),
            total,
        ),
        "rule_response_version": recovery_rate(
            sum(event.rule_response_version is not None for event in events),
            total,
        ),
        "correlation_confidence": correlation_counts.most_common(),
        "duplicate_records_removed": batch.duplicate_records_removed,
        "legacy_schema_records_excluded": batch.legacy_schema_records,
    }


def _segments(batch: NormalizationResult) -> ObjectDict:
    segments: ObjectDict = {}
    for mode in sorted({event.enforcement_mode for event in batch.events}):
        mode_events = [
            event for event in batch.events if event.enforcement_mode == mode
        ]
        segments[mode] = {
            "events": len(mode_events),
            "findings": sum(len(event.distinct_findings()) for event in mode_events),
            "sessions": len({event.session_id for event in mode_events}),
            "repositories": len(
                {
                    event.resolved_repo_root
                    for event in mode_events
                    if event.resolved_repo_root is not None
                }
            ),
        }
    return segments


def _scoped_recovery(batch: NormalizationResult, scope: RecoveryScope) -> ObjectDict:
    if scope is RecoveryScope.ALL:
        return {
            "scope": scope.value,
            "scope_reports": {
                selected.value: recovery_report(
                    scoped_events(batch.events, selected),
                    batch.duplicate_records_removed,
                )
                for selected in (
                    RecoveryScope.MANAGED,
                    RecoveryScope.RELAXED,
                    RecoveryScope.GLOBAL,
                )
            },
        }
    report = recovery_report(
        scoped_events(batch.events, scope),
        batch.duplicate_records_removed,
    )
    report["scope"] = scope.value
    return report


def analyze(
    entries: list[ObjectDict], *, scope: RecoveryScope = RecoveryScope.MANAGED
) -> ObjectDict:
    """Build a schema-versioned report without mixing event and finding units."""
    batch = normalize_entries(entries)
    counters = _Counters()
    for event in batch.events:
        _accumulate_result(event, counters)
    dates = sorted(counters.daily_counts)
    date_range = f"{dates[0]} to {dates[-1]}" if dates else UNKNOWN_VALUE
    finding_total = sum(counters.finding_decisions.values())
    recovery = _scoped_recovery(batch, scope)
    representative_sequences = recovery.get("representative_sequences", [])
    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "trace_schema_versions_seen": list(batch.trace_schema_versions_seen),
        "raw_total_events": batch.raw_total_events,
        "analyzed_events": len(batch.events),
        "total_events": len(batch.events),
        "fixture_filtered": batch.fixture_filtered,
        "date_range": date_range,
        "by_event": counters.by_event.most_common(),
        "by_decision": counters.finding_decisions.most_common(),
        "by_severity": counters.by_severity.most_common(),
        "top_rules_denied": counters.enforcement_rules.most_common(
            STATS_TOP_RULE_LIMIT
        ),
        "top_rules_enforced": counters.enforcement_rules.most_common(
            STATS_TOP_RULE_LIMIT
        ),
        "advisory_rules": counters.advisory_rules.most_common(STATS_TOP_RULE_LIMIT),
        "enrichment_rules": counters.enrichment_rules.most_common(STATS_TOP_RULE_LIMIT),
        "top_files_denied": counters.denied_files.most_common(15),
        "top_tools": counters.by_tool.most_common(10),
        "sessions": len(counters.by_session),
        "daily_counts": sorted(counters.daily_counts.items()),
        "rule_examples": dict(counters.rule_examples),
        "legacy_metrics": {
            "status": "deprecated",
            "legacy_churn": legacy_churn(batch.events),
        },
        "event_outcomes": _distribution(counters.event_outcomes, len(batch.events)),
        "finding_decisions": _distribution(counters.finding_decisions, finding_total),
        "recovery": recovery,
        "telemetry_coverage": _coverage(batch),
        "segments": _segments(batch),
        "representative_sequences": representative_sequences,
    }
