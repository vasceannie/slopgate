"""Comparison evaluation: cohort filtering, facets, deltas, aggregation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from slopgate._types import ObjectDict, is_object_dict, object_dict, object_list
from slopgate.constants import PLATFORM_KEY

from ..episodes import evaluate_episodes
from ..metrics import (
    DELTA_PRECISION,
    comparison_snapshot_metrics,
)
from ..scope_model import ResultRecord
from .selectors import (
    ENTRY_COHORT_FIELDS,
    LANGUAGE_COHORT,
    RULE_COHORT,
    SCOPE_CONFIDENCE_COHORT,
    ComparisonSpec,
)

# Reported as facet breakdowns on both sides.
FACET_DIMENSIONS = (
    "repo",
    "enforcement_mode",
    PLATFORM_KEY,
    "capability",
    "model",
    "provider",
    "language",
    "version",
    "scope_confidence",
    "rule",
    "policy",
    "guidance",
)
# Dims that must be single-valued and equal for the headline aggregate.
GATING_DIMENSIONS = (
    "repo",
    "enforcement_mode",
    PLATFORM_KEY,
    "capability",
    "model",
    "provider",
    "language",
    "version",
)

DELTA_METRICS = (
    ("blocking_per_100_mutations", "value"),
    ("first_attempt_clean_rate", "rate"),
    ("repair_success_rate", "rate"),
    ("repair_attempts", "median"),
    ("repair_latency_ms", "median"),
    ("evaluation_ms_p95", "value"),
)


def build_comparison(
    records: Sequence[ResultRecord], spec: ComparisonSpec
) -> tuple[ObjectDict | None, str | None]:
    """Return the comparison payload or an error string."""
    field = (
        "policy_fingerprint" if spec.dimension == "policy" else "guidance_fingerprint"
    )
    filtered = apply_cohort_filters(records, spec.cohorts)
    eligible = [
        record
        for record in filtered
        if not record.legacy and getattr(record, field) is not None
    ]
    present = {getattr(record, field) for record in eligible}
    missing = [
        label
        for label, value in (("baseline", spec.baseline), ("candidate", spec.candidate))
        if value not in present
    ]
    if missing:
        return None, (
            f"{spec.dimension} fingerprint not present in trace data: "
            f"{', '.join(missing)}"
        )
    baseline_rows = [
        record for record in eligible if getattr(record, field) == spec.baseline
    ]
    candidate_rows = [
        record for record in eligible if getattr(record, field) == spec.candidate
    ]
    return _comparison_payload(spec, baseline_rows, candidate_rows), None


def apply_cohort_filters(
    records: Sequence[ResultRecord], cohorts: Sequence[tuple[str, str]]
) -> list[ResultRecord]:
    """Keep records matching every entry-level cohort filter."""
    field_filters = [
        (ENTRY_COHORT_FIELDS[dimension], value)
        for dimension, value in cohorts
        if dimension in ENTRY_COHORT_FIELDS
    ]
    language_filters = [
        value for dimension, value in cohorts if dimension == LANGUAGE_COHORT
    ]
    rule_filters = [value for dimension, value in cohorts if dimension == RULE_COHORT]
    confidence_filters = [
        value
        for dimension, value in cohorts
        if dimension == SCOPE_CONFIDENCE_COHORT
    ]
    return [
        record
        for record in records
        if _matches_fields(record, field_filters)
        and _matches_languages(record, language_filters)
        and _matches_rules(record, rule_filters)
        and _matches_scope_confidence(record, confidence_filters)
    ]


def _matches_fields(
    record: ResultRecord, field_filters: Sequence[tuple[str, str]]
) -> bool:
    for field, value in field_filters:
        record_value = getattr(record, field)
        if record_value is None or str(record_value) != value:
            return False
    return True


def _matches_languages(
    record: ResultRecord, language_filters: Sequence[str]
) -> bool:
    if not language_filters:
        return True
    return all(language in record.languages for language in language_filters)


def _matches_rules(record: ResultRecord, rule_filters: Sequence[str]) -> bool:
    return all(rule in record.blocking_rules for rule in rule_filters)


def _matches_scope_confidence(
    record: ResultRecord, confidence_filters: Sequence[str]
) -> bool:
    return all(record.scope_confidence == value for value in confidence_filters)


def _comparison_payload(
    spec: ComparisonSpec,
    baseline_rows: Sequence[ResultRecord],
    candidate_rows: Sequence[ResultRecord],
) -> ObjectDict:
    baseline = _side_snapshot(baseline_rows, spec.baseline)
    candidate = _side_snapshot(candidate_rows, spec.candidate)
    facets: ObjectDict = {
        dimension: {
            "baseline": _facet_pairs(baseline_rows, dimension),
            "candidate": _facet_pairs(candidate_rows, dimension),
        }
        for dimension in FACET_DIMENSIONS
    }
    confounding = _confounding_dimensions(facets, spec.dimension)
    reason = None
    if confounding:
        reason = (
            "aggregate suppressed: cohorts differ in "
            f"{', '.join(confounding)}; review stratified breakdowns"
        )
    return {
        "dimension": spec.dimension,
        "baseline": baseline,
        "candidate": candidate,
        "matched_dimensions": [dimension for dimension, _value in spec.cohorts],
        "metric_deltas": _metric_deltas(baseline, candidate),
        "facets": facets,
        "confounding_dimensions": confounding,
        "aggregate": {"available": not confounding, "suppression_reason": reason},
    }


def _side_snapshot(rows: Sequence[ResultRecord], fingerprint: str) -> ObjectDict:
    evaluation = evaluate_episodes(list(rows))
    window, runtime, evaluation_p95 = comparison_snapshot_metrics(rows, evaluation)
    return {
        "fingerprint": fingerprint,
        "window": window,
        "runtime": runtime,
        "evaluation_ms_p95": {"value": evaluation_p95},
        "sample_counts": {
            "results": len(rows),
            "mutating_results": sum(1 for record in rows if record.mutating),
            "episodes": len(evaluation.episodes),
            "first_observed_scopes": len(evaluation.first_observed),
        },
    }


def _facet_pairs(rows: Sequence[ResultRecord], dimension: str) -> list[list[object]]:
    counter: Counter[str] = Counter()
    for record in rows:
        for value in _facet_values(record, dimension):
            counter[value] += 1
    return [[value, count] for value, count in counter.most_common()]


def _facet_values(record: ResultRecord, dimension: str) -> list[str]:
    if dimension == LANGUAGE_COHORT:
        return list(record.languages)
    if dimension == "rule":
        return list(record.blocking_rules)
    if dimension == "scope_confidence":
        return [record.scope_confidence]
    value = getattr(record, ENTRY_COHORT_FIELDS[dimension])
    return [str(value)] if value is not None else ["unknown"]


def _confounding_dimensions(facets: ObjectDict, intervention: str) -> list[str]:
    confounding: list[str] = []
    for dimension in GATING_DIMENSIONS:
        sides = object_dict(facets.get(dimension))
        if not sides:
            continue
        baseline_values = _facet_value_set(sides.get("baseline"))
        candidate_values = _facet_value_set(sides.get("candidate"))
        if len(baseline_values) > 1 or len(candidate_values) > 1:
            confounding.append(dimension)
        elif baseline_values != candidate_values:
            confounding.append(dimension)
    non_selected = "guidance" if intervention == "policy" else "policy"
    if _fingerprint_sides_differ(facets, non_selected):
        confounding.append(f"{non_selected}_fingerprint")
    return confounding


def _fingerprint_sides_differ(facets: ObjectDict, dimension: str) -> bool:
    sides = object_dict(facets.get(dimension))
    if not sides:
        return True
    baseline_values = _facet_value_set(sides.get("baseline"))
    candidate_values = _facet_value_set(sides.get("candidate"))
    return baseline_values != candidate_values


def _facet_value_set(raw_pairs: object) -> set[object]:
    return {
        pair[0]
        for raw_pair in object_list(raw_pairs)
        if len(pair := object_list(raw_pair)) >= 2
    }


def _metric_deltas(baseline: ObjectDict, candidate: ObjectDict) -> ObjectDict:
    deltas: ObjectDict = {}
    baseline_metrics = {**object_dict(baseline.get("window")), **baseline}
    candidate_metrics = {**object_dict(candidate.get("window")), **candidate}
    for metric, field in DELTA_METRICS:
        baseline_payload = baseline_metrics.get(metric)
        candidate_payload = candidate_metrics.get(metric)
        if not is_object_dict(baseline_payload) or not is_object_dict(
            candidate_payload
        ):
            continue
        deltas[metric] = _delta(
            baseline_payload.get(field), candidate_payload.get(field)
        )
    return deltas


def _delta(baseline: object, candidate: object) -> ObjectDict:
    if not isinstance(baseline, (int, float)) or not isinstance(
        candidate, (int, float)
    ):
        return {
            "baseline": baseline,
            "candidate": candidate,
            "absolute": None,
            "relative": None,
        }
    absolute = round(candidate - baseline, DELTA_PRECISION)
    relative = None
    if baseline != 0:
        relative = round((candidate - baseline) / baseline * 100.0, DELTA_PRECISION)
    return {
        "baseline": baseline,
        "candidate": candidate,
        "absolute": absolute,
        "relative": relative,
    }
