"""Normalize raw ``results.jsonl`` dictionaries into typed records."""

from __future__ import annotations

from enum import Enum
from typing import Final, TypeVar

from slopgate._types import ObjectDict, object_dict, object_list
from slopgate.constants import (
    MAX_RECOVERY_CANDIDATE_PATHS,
    MAX_RECOVERY_COLLECTOR_VARIANTS,
    MAX_RECOVERY_FINDINGS,
    METADATA_COMMAND,
    METADATA_DECISION,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    SESSION_ID,
    UNKNOWN_VALUE,
)
from slopgate.util.metadata_paths import effective_metadata_path

from .dedupe import dedupe_entries
from .records import (
    CorrelationConfidence,
    EventOutcome,
    FindingDecision,
    NormalizationResult,
    NormalizedEvent,
    NormalizedFinding,
    RecoveryTarget,
    RepairPlanState,
    TargetType,
    ToolOutcome,
)

TRACE_SCHEMA_VERSION: Final = 2
POST_TOOL_FAILURE: Final = "PostToolUseFailure"
_EnumValue = TypeVar("_EnumValue", bound=Enum)


def _normalized_strings(value: object, *, limit: int | None = None) -> tuple[str, ...]:
    normalized = (
        item.strip()
        for item in object_list(value)
        if isinstance(item, str) and item.strip()
    )
    unique = tuple(dict.fromkeys(normalized))
    return unique if limit is None else unique[:limit]


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _parse_enum(enum_type: type[_EnumValue], value: object) -> _EnumValue | None:
    if not isinstance(value, str):
        return None
    try:
        return enum_type(value)
    except ValueError:
        return None


def _classify_result(
    entry: ObjectDict,
    findings: tuple[NormalizedFinding, ...],
    *,
    is_legacy: bool,
) -> EventOutcome:
    explicit = _parse_enum(EventOutcome, entry.get("event_outcome"))
    if explicit is not None:
        return explicit
    if is_legacy:
        return EventOutcome.UNKNOWN
    if object_list(entry.get("errors")):
        return EventOutcome.EVALUATION_ERROR
    event_name = str(entry.get("event_name", UNKNOWN_VALUE))
    if event_name == POST_TOOL_FAILURE:
        return EventOutcome.TOOL_FAILED
    decisions = {finding.decision for finding in findings}
    if FindingDecision.DENY in decisions or FindingDecision.BLOCK in decisions:
        if event_name in {PRE_TOOL_USE, PERMISSION_REQUEST}:
            return EventOutcome.BLOCKED_PRE_TOOL
        if event_name == POST_TOOL_USE:
            return EventOutcome.BLOCKED_POST_TOOL
        return EventOutcome.UNKNOWN
    if FindingDecision.ASK in decisions:
        return EventOutcome.ASKED
    return EventOutcome.PASSED_WITH_ADVISORY if findings else EventOutcome.PASSED_CLEAN


def _tool_result(entry: ObjectDict) -> ToolOutcome:
    explicit = _parse_enum(ToolOutcome, entry.get("tool_outcome"))
    if explicit is not None:
        return explicit
    if entry.get("event_name") == POST_TOOL_FAILURE:
        return ToolOutcome.FAILURE
    return ToolOutcome.UNKNOWN


def _confidence(entry: ObjectDict) -> CorrelationConfidence:
    explicit = _parse_enum(
        CorrelationConfidence,
        entry.get("correlation_confidence"),
    )
    if explicit is not None:
        return explicit
    if _optional_string(entry.get("operation_id")) is not None:
        return CorrelationConfidence.EXACT
    has_session = _optional_string(entry.get(SESSION_ID)) is not None
    has_target = bool(_normalized_strings(entry.get("candidate_paths"))) or (
        _optional_string(entry.get("resolved_repo_root")) is not None
    )
    if has_session and has_target:
        return CorrelationConfidence.INFERRED
    return CorrelationConfidence.UNAVAILABLE


def _repair_state(entry: ObjectDict) -> RepairPlanState:
    value = _parse_enum(RepairPlanState, entry.get("repair_plan_state"))
    return value if value is not None else RepairPlanState.NONE


def _targets(
    entry: ObjectDict,
    finding: ObjectDict,
    candidate_paths: tuple[str, ...],
) -> tuple[RecoveryTarget, ...]:
    metadata_path = effective_metadata_path(object_dict(finding.get("metadata")))
    if metadata_path is not None:
        return (RecoveryTarget(TargetType.FILE, metadata_path),)
    if candidate_paths:
        return tuple(RecoveryTarget(TargetType.FILE, path) for path in candidate_paths)
    fallback_fields: tuple[tuple[TargetType, str], ...] = (
        (TargetType.COMMAND, METADATA_COMMAND),
        (TargetType.REPOSITORY, "resolved_repo_root"),
        (TargetType.SESSION, SESSION_ID),
    )
    for target_type, field_name in fallback_fields:
        value = _optional_string(entry.get(field_name))
        if value is not None:
            return (RecoveryTarget(target_type, value),)
    return (RecoveryTarget(TargetType.UNKNOWN, UNKNOWN_VALUE),)


def _parse_findings(
    entry: ObjectDict,
    candidate_paths: tuple[str, ...],
) -> tuple[NormalizedFinding, ...]:
    normalized: list[NormalizedFinding] = []
    for source_finding_index, raw_finding in enumerate(
        object_list(entry.get("findings"))[:MAX_RECOVERY_FINDINGS]
    ):
        finding = object_dict(raw_finding)
        if not finding:
            continue
        rule_id = str(finding.get("rule_id", UNKNOWN_VALUE))
        metadata = object_dict(finding.get("metadata"))
        variants = _normalized_strings(
            metadata.get("failing_collectors"),
            limit=MAX_RECOVERY_COLLECTOR_VARIANTS,
        )
        if rule_id != "QUALITY-LINT-001" or not variants:
            variants = (None,)
        decision = _parse_enum(FindingDecision, finding.get(METADATA_DECISION))
        if decision is None:
            decision = FindingDecision.NO_EXPLICIT_DECISION
        finding_targets = _targets(entry, finding, candidate_paths)
        for variant in variants:
            normalized.append(
                NormalizedFinding(
                    source_finding_index=source_finding_index,
                    rule_id=rule_id,
                    rule_variant=variant,
                    decision=decision,
                    severity=str(finding.get("severity", UNKNOWN_VALUE)),
                    message=str(finding.get("message", "")),
                    targets=finding_targets,
                )
            )
    return tuple(normalized)


def _parse_result(source_index: int, entry: ObjectDict) -> NormalizedEvent:
    candidate_paths = _normalized_strings(
        entry.get("candidate_paths"),
        limit=MAX_RECOVERY_CANDIDATE_PATHS,
    )
    findings = _parse_findings(entry, candidate_paths)
    trace_schema_version = _integer(entry.get("trace_schema_version"))
    is_legacy = trace_schema_version != TRACE_SCHEMA_VERSION
    return NormalizedEvent(
        source_index=source_index,
        timestamp=str(entry.get("timestamp", "")),
        trace_schema_version=trace_schema_version,
        evaluation_id=_optional_string(entry.get("evaluation_id")),
        operation_id=_optional_string(entry.get("operation_id")),
        correlation_confidence=_confidence(entry),
        session_id=str(entry.get(SESSION_ID, UNKNOWN_VALUE)),
        event_name=str(entry.get("event_name", UNKNOWN_VALUE)),
        event_outcome=_classify_result(entry, findings, is_legacy=is_legacy),
        tool_name=str(entry.get("tool_name", "")) or "(none)",
        tool_outcome=_tool_result(entry),
        candidate_paths=candidate_paths,
        attempt_fingerprint=_optional_string(entry.get("attempt_fingerprint")),
        resolved_repo_root=_optional_string(entry.get("resolved_repo_root")),
        enforcement_mode=str(entry.get("enforcement_mode", "unavailable")),
        platform_capability=str(entry.get("platform_capability", UNKNOWN_VALUE)),
        rule_response_version=_optional_string(entry.get("rule_response_version")),
        intervention_tags=_normalized_strings(entry.get("intervention_tags")),
        repair_plan_state=_repair_state(entry),
        findings=findings,
        is_legacy=is_legacy,
    )


def normalize_entries(entries: list[ObjectDict]) -> NormalizationResult:
    """Normalize, fixture-filter, and deterministically deduplicate result records."""
    deduplicated = dedupe_entries(entries)
    retained: list[tuple[int, ObjectDict]] = []
    fixture_filtered = 0
    for index, entry in deduplicated.entries:
        session_id = str(entry.get(SESSION_ID, UNKNOWN_VALUE))
        if session_id.startswith(("fixture-", "test-", "self-test-")):
            fixture_filtered += 1
            continue
        retained.append((index, entry))
    events = tuple(_parse_result(index, entry) for index, entry in retained)
    versions = tuple(
        sorted(
            {
                event.trace_schema_version
                for event in events
                if event.trace_schema_version is not None
            }
        )
    )
    return NormalizationResult(
        events=events,
        raw_total_events=len(entries),
        fixture_filtered=fixture_filtered,
        duplicate_records_removed=deduplicated.duplicate_records_removed,
        legacy_schema_records=sum(event.is_legacy for event in events),
        trace_schema_versions_seen=versions,
    )
