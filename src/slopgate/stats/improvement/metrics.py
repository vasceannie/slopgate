"""Improvement metric assembly for the nested stats improvement object.

Every rate exposes raw numerator, denominator, and censored counts so
downstream consumers never reverse-engineer percentages. The headline uses
``repo_strict`` only; relaxed and outside-repo cohorts stay visible in
``by_enforcement_mode`` so disabling enforcement cannot masquerade as
improvement.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Sequence

from slopgate._types import ObjectDict
from slopgate.constants import STATS_TOP_RULE_LIMIT

from .episodes import evaluate_episodes, parse_result_records
from .scope_model import (
    EPISODE_TERMINAL_STATES,
    OUTSIDE_MODE,
    RELAXED_MODE,
    STRICT_MODE,
    UNKNOWN_POLICY,
    UNKNOWN_VALUE,
    UNKNOWN_VERSION,
    EpisodeEvaluation,
    RepairEpisode,
    ResultRecord,
)

IMPROVEMENT_SCHEMA_VERSION = 1
COHORT_REPORT_CAP = STATS_TOP_RULE_LIMIT
RATE_PRECISION = 4
PER100_PRECISION = 2
STATS_PRECISION = 1
DELTA_PRECISION = 2
PERCENTILE_MEDIAN = 0.5
PERCENTILE_P90 = 0.9
PERCENTILE_P95 = 0.95
CENSORED_STATES = (
    "no_observed_followup",
    "provenance_changed",
    "evaluation_error",
)

_FacetPicker = Callable[[ResultRecord], Sequence[str]]


def build_improvement(entries: Sequence[object]) -> ObjectDict:
    """Build the versioned improvement object for one stats window."""
    records = parse_result_records(entries)
    evaluation = evaluate_episodes(records)
    legacy_count = sum(1 for record in records if record.legacy)
    authoritative = any(not record.legacy for record in records)
    return {
        "schema_version": IMPROVEMENT_SCHEMA_VERSION,
        "authoritative": authoritative,
        "legacy_rows": {"count": legacy_count, "included_in_comparisons": False},
        "headline": _headline_metrics(records, evaluation, STRICT_MODE),
        "by_enforcement_mode": _by_enforcement_mode(records, evaluation),
        "by_rule": _by_rule(evaluation),
        "cohorts": _cohorts(records),
        "episodes": _episode_summary(evaluation),
        "runtime": _runtime(records),
        "comparison": None,
    }


def _rate(numerator: int, denominator: int) -> ObjectDict:
    rate = round(numerator / denominator, RATE_PRECISION) if denominator else None
    return {"rate": rate, "numerator": numerator, "denominator": denominator}


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], STATS_PRECISION)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[int(position)], STATS_PRECISION)
    weight = position - lower
    interpolated = ordered[lower] * (1.0 - weight) + ordered[upper] * weight
    return round(interpolated, STATS_PRECISION)


def _mode_records(
    records: Sequence[ResultRecord], mode: str
) -> list[ResultRecord]:
    return [record for record in records if record.enforcement_mode == mode]


def _mode_episodes(
    evaluation: EpisodeEvaluation, mode: str
) -> list[RepairEpisode]:
    return [
        episode
        for episode in evaluation.episodes
        if episode.anchor.enforcement_mode == mode
    ]


def _blocking_per_100(records: Sequence[ResultRecord]) -> ObjectDict:
    mutating = [record for record in records if record.mutating]
    blocked = sum(1 for record in mutating if record.blocking_rules)
    value = round(100.0 * blocked / len(mutating), PER100_PRECISION) if mutating else None
    return {"value": value, "numerator": blocked, "denominator": len(mutating)}


def _first_attempt_clean(firsts: Sequence[ResultRecord]) -> ObjectDict:
    clean = sum(1 for record in firsts if not record.blocking_rules)
    return _rate(clean, len(firsts))


def _repair_success(episodes: Sequence[RepairEpisode]) -> ObjectDict:
    states = Counter(episode.state for episode in episodes)
    resolved = states.get("resolved", 0)
    still_failing = states.get("still_failing", 0)
    payload = _rate(resolved, resolved + still_failing)
    payload["censored"] = {
        state: states.get(state, 0) for state in CENSORED_STATES
    }
    return payload


def _repair_distributions(episodes: Sequence[RepairEpisode]) -> ObjectDict:
    resolved = [
        episode for episode in episodes if episode.resolved_record is not None
    ]
    attempts = [float(episode.attempts) for episode in resolved]
    latencies = [
        episode.latency_ms
        for episode in resolved
        if episode.latency_ms is not None
    ]
    return {
        "repair_attempts": {
            "median": _percentile(attempts, PERCENTILE_MEDIAN),
            "p90": _percentile(attempts, PERCENTILE_P90),
        },
        "repair_latency_ms": {
            "median": _percentile(latencies, PERCENTILE_MEDIAN),
            "p90": _percentile(latencies, PERCENTILE_P90),
        },
    }


def _window_metrics(
    records: Sequence[ResultRecord],
    first_observed: Sequence[ResultRecord],
    episodes: Sequence[RepairEpisode],
) -> ObjectDict:
    """Compute headline metrics over an explicit record/episode window."""
    payload: ObjectDict = {
        "blocking_per_100_mutations": _blocking_per_100(records),
        "first_attempt_clean_rate": _first_attempt_clean(first_observed),
        "repair_success_rate": _repair_success(episodes),
    }
    payload.update(_repair_distributions(episodes))
    return payload


def _headline_metrics(
    records: Sequence[ResultRecord],
    evaluation: EpisodeEvaluation,
    mode: str,
) -> ObjectDict:
    mode_records = _mode_records(records, mode)
    mode_episodes = _mode_episodes(evaluation, mode)
    mode_first_observed = [
        record
        for record in evaluation.first_observed
        if record.enforcement_mode == mode
    ]
    return _window_metrics(mode_records, mode_first_observed, mode_episodes)


def _by_enforcement_mode(
    records: Sequence[ResultRecord], evaluation: EpisodeEvaluation
) -> ObjectDict:
    modes = sorted({record.enforcement_mode for record in records})
    known = [mode for mode in (STRICT_MODE, RELAXED_MODE, OUTSIDE_MODE) if mode in modes]
    known.extend(mode for mode in modes if mode not in known)
    return {
        mode: _headline_metrics(records, evaluation, mode) for mode in known
    }


def _by_rule(evaluation: EpisodeEvaluation) -> ObjectDict:
    grouped: dict[str, list[RepairEpisode]] = {}
    for episode in evaluation.episodes:
        grouped.setdefault(episode.rule_id, []).append(episode)
    payload: ObjectDict = {}
    for rule_id in sorted(grouped):
        episodes = grouped[rule_id]
        followups = evaluation.rule_followups.get(rule_id, 0)
        enforcing = evaluation.rule_enforcing_followups.get(rule_id, 0)
        entry = _repair_success(episodes)
        entry["persistence_rate"] = _rate(enforcing, followups)
        entry["episode_count"] = len(episodes)
        payload[rule_id] = entry
    return payload


def _episode_summary(evaluation: EpisodeEvaluation) -> ObjectDict:
    states = Counter(episode.state for episode in evaluation.episodes)
    summary: ObjectDict = {"total": len(evaluation.episodes)}
    for state in EPISODE_TERMINAL_STATES:
        summary[state] = states.get(state, 0)
    summary.update(_repair_distributions(evaluation.episodes))
    summary["scope_confidence"] = _pairs(
        Counter(episode.anchor.scope_confidence for episode in evaluation.episodes)
    )
    return summary


def _runtime(records: Sequence[ResultRecord]) -> ObjectDict:
    total = len(records)
    errored = sum(1 for record in records if record.has_errors)
    evaluation_ms = [
        record.evaluation_ms
        for record in records
        if record.evaluation_ms is not None
    ]
    engine_ms = [
        record.rule_engine_ms
        for record in records
        if record.rule_engine_ms is not None
    ]
    return {
        "result_error_rate": _rate(errored, total),
        "evaluation_ms": {
            "p50": _percentile(evaluation_ms, PERCENTILE_MEDIAN),
            "p95": _percentile(evaluation_ms, PERCENTILE_P95),
        },
        "rule_engine_ms": {
            "p50": _percentile(engine_ms, PERCENTILE_MEDIAN),
            "p95": _percentile(engine_ms, PERCENTILE_P95),
        },
    }


def comparison_snapshot_metrics(
    records: Sequence[ResultRecord], evaluation: EpisodeEvaluation
) -> tuple[ObjectDict, ObjectDict, float | None]:
    """Build the metric primitives used by one comparison side."""
    rows = list(records)
    window = _window_metrics(rows, evaluation.first_observed, evaluation.episodes)
    runtime = _runtime(rows)
    evaluation_p95 = _percentile(
        [record.evaluation_ms for record in rows if record.evaluation_ms is not None],
        PERCENTILE_P95,
    )
    return window, runtime, evaluation_p95


def _pairs(counter: Counter[str]) -> list[list[object]]:
    return [[value, count] for value, count in counter.most_common(COHORT_REPORT_CAP)]


def _facet(records: Sequence[ResultRecord], picker: _FacetPicker) -> list[list[object]]:
    counter: Counter[str] = Counter()
    for record in records:
        for value in picker(record):
            counter[value] += 1
    return _pairs(counter)


def _cohorts(records: Sequence[ResultRecord]) -> ObjectDict:
    facets: dict[str, _FacetPicker] = {
        "repo": lambda record: [record.repo_root or UNKNOWN_VALUE],
        "enforcement_mode": lambda record: [record.enforcement_mode],
        "platform": lambda record: [record.platform],
        "platform_capability": lambda record: [
            record.platform_capability or UNKNOWN_VALUE
        ],
        "model": lambda record: [record.model or UNKNOWN_VALUE],
        "provider": lambda record: [record.provider or UNKNOWN_VALUE],
        "semantic_family": lambda record: [record.family],
        "language": lambda record: list(record.languages) or [UNKNOWN_VALUE],
        "slopgate_version": lambda record: [
            record.slopgate_version or UNKNOWN_VERSION
        ],
        "effective_policy_fingerprint": lambda record: [
            record.policy_fingerprint or UNKNOWN_POLICY
        ],
        "guidance_fingerprint": lambda record: [
            record.guidance_fingerprint or UNKNOWN_POLICY
        ],
        "scope_confidence": lambda record: [record.scope_confidence],
        "rule": lambda record: list(record.blocking_rules),
    }
    return {name: _facet(records, picker) for name, picker in facets.items()}
