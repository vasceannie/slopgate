"""Actionable per-rule evidence over deterministic recovery chains."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from slopgate._types import ObjectDict

from .chains import (
    ChainState,
    ChainStatus,
    build_chains,
    recovery_rate,
    summarize_chains,
)
from .records import NormalizedEvent
from .sequences import representative_sequences


@dataclass(frozen=True, slots=True)
class _ClassificationEvidence:
    first_retries: int
    rule_clearances: int
    fingerprint_observations: int
    operation_observations: int
    unchanged: int
    changed: int
    operation_successes: int
    operation_failures: int
    recovered: int
    abandoned: int
    open_censored: int
    session_outlier: bool
    repository_outlier: bool
    compound_friction: bool

    @classmethod
    def from_chains(cls, chains: list[ChainState]) -> _ClassificationEvidence:
        counts: Counter[str] = Counter()
        sessions: Counter[str] = Counter()
        repositories: Counter[str | None] = Counter()
        compound_friction = False
        for state in chains:
            counts["first_retries"] += state.first_rule_cleared is not None
            counts["rule_clearances"] += state.first_rule_cleared is True
            counts["fingerprint_observations"] += (
                state.first_fingerprint_unchanged is not None
            )
            counts["operation_observations"] += (
                state.first_operation_succeeded is not None
            )
            counts["unchanged"] += state.first_fingerprint_unchanged is True
            counts["changed"] += state.first_fingerprint_unchanged is False
            counts["operation_successes"] += state.first_operation_succeeded is True
            counts["operation_failures"] += state.first_operation_succeeded is False
            counts["recovered"] += state.status is ChainStatus.RECOVERED
            counts["abandoned"] += state.status is ChainStatus.ABANDONED
            counts["open_censored"] += state.status is ChainStatus.OPEN
            sessions[state.key.session_id] += 1
            repositories[state.key.repo_root] += 1
            compound_friction |= state.compound_first_retry_blocked
        repositories.pop(None, None)
        return cls(
            first_retries=counts["first_retries"],
            rule_clearances=counts["rule_clearances"],
            fingerprint_observations=counts["fingerprint_observations"],
            operation_observations=counts["operation_observations"],
            unchanged=counts["unchanged"],
            changed=counts["changed"],
            operation_successes=counts["operation_successes"],
            operation_failures=counts["operation_failures"],
            recovered=counts["recovered"],
            abandoned=counts["abandoned"],
            open_censored=counts["open_censored"],
            session_outlier=(
                len(sessions) > 1 and max(sessions.values()) * 2 > len(chains)
            ),
            repository_outlier=(
                len(repositories) > 1 and max(repositories.values()) * 2 > len(chains)
            ),
            compound_friction=compound_friction,
        )


@dataclass(frozen=True, slots=True)
class _ClassificationSpec:
    name: str
    matches: Callable[[_ClassificationEvidence], bool]


_CLASSIFICATIONS: Final = (
    _ClassificationSpec(
        "insufficient_telemetry",
        lambda evidence: not evidence.first_retries
        or not evidence.fingerprint_observations
        or not evidence.operation_observations,
    ),
    _ClassificationSpec("session_outlier", lambda evidence: evidence.session_outlier),
    _ClassificationSpec(
        "repository_outlier", lambda evidence: evidence.repository_outlier
    ),
    _ClassificationSpec(
        "workflow_disruption", lambda evidence: evidence.abandoned > evidence.recovered
    ),
    _ClassificationSpec(
        "compound_rule_friction", lambda evidence: evidence.compound_friction
    ),
    _ClassificationSpec(
        "unchanged_retry_pressure",
        lambda evidence: evidence.unchanged > evidence.changed,
    ),
    _ClassificationSpec(
        "remediation_friction",
        lambda evidence: evidence.changed > evidence.unchanged
        and evidence.operation_failures > evidence.operation_successes,
    ),
)


def _share(counter: Counter[str]) -> ObjectDict:
    total = sum(counter.values())
    return recovery_rate(max(counter.values(), default=0), total)


def _classifications(evidence: _ClassificationEvidence) -> list[str]:
    flags = [spec.name for spec in _CLASSIFICATIONS if spec.matches(evidence)]
    return flags or ["healthy_high_volume"]


def _rule_row(chains: list[ChainState]) -> ObjectDict:
    first = chains[0]
    evidence = _ClassificationEvidence.from_chains(chains)
    sessions = Counter(state.key.session_id for state in chains)
    repositories = Counter(
        state.key.repo_root for state in chains if state.key.repo_root is not None
    )
    classifications = _classifications(evidence)
    return {
        "label": (
            first.key.rule_id
            if first.key.rule_variant is None
            else f"{first.key.rule_id} / {first.key.rule_variant}"
        ),
        "rule_id": first.key.rule_id,
        "rule_variant": first.key.rule_variant,
        "chains": len(chains),
        "sessions": len(sessions),
        "repositories": len(repositories),
        "top_session_share": _share(sessions),
        "top_repository_share": _share(repositories),
        "first_retry_rule_clearance": recovery_rate(
            evidence.rule_clearances,
            evidence.first_retries,
        ),
        "first_retry_operation_success": recovery_rate(
            evidence.operation_successes,
            evidence.operation_observations,
        ),
        "unchanged_first_retry": recovery_rate(
            evidence.unchanged,
            evidence.fingerprint_observations,
        ),
        "changed_first_retry": recovery_rate(
            evidence.changed,
            evidence.fingerprint_observations,
        ),
        "eventual_recovery": recovery_rate(
            evidence.recovered,
            evidence.recovered + evidence.abandoned,
        ),
        "abandoned": evidence.abandoned,
        "open_censored": evidence.open_censored,
        "classifications": classifications,
        "primary_classification": classifications[0],
    }


def _ratio(numerator: int, denominator: int, unavailable: float) -> float:
    return numerator / denominator if denominator else unavailable


def _friction_priority(chains: list[ChainState]) -> tuple[object, ...]:
    evidence = _ClassificationEvidence.from_chains(chains)
    first = chains[0]
    insufficient = (
        not evidence.first_retries
        or not evidence.fingerprint_observations
        or not evidence.operation_observations
    )
    sessions = len({state.key.session_id for state in chains})
    repositories = len(
        {state.key.repo_root for state in chains if state.key.repo_root is not None}
    )
    return (
        1 if insufficient else 0,
        -_ratio(evidence.unchanged, evidence.fingerprint_observations, 0.0),
        _ratio(evidence.operation_successes, evidence.operation_observations, 1.0),
        -_ratio(
            evidence.abandoned,
            evidence.recovered + evidence.abandoned,
            0.0,
        ),
        -repositories,
        -sessions,
        first.key.rule_id,
        first.key.rule_variant or "",
    )


def _interventions(chains: list[ChainState]) -> list[ObjectDict]:
    tagged: dict[str, list[ChainState]] = defaultdict(list)
    for state in chains:
        tags = set(state.initial.intervention_tags)
        for retry in state.retries:
            tags.update(retry.intervention_tags)
        for tag in tags:
            tagged[tag].append(state)
    return [
        {
            "tag": tag,
            "recovery": recovery_rate(
                sum(state.status is ChainStatus.RECOVERED for state in states),
                len(states),
            ),
        }
        for tag, states in sorted(tagged.items())
    ]


def recovery_report(
    events: tuple[NormalizedEvent, ...], duplicate_records_removed: int
) -> ObjectDict:
    """Build summary, rule evidence, and structured-intervention recovery metrics."""
    chains = build_chains(events)
    report = summarize_chains(chains)
    grouped: dict[tuple[str, str | None], list[ChainState]] = defaultdict(list)
    for state in chains:
        grouped[(state.key.rule_id, state.key.rule_variant)].append(state)
    ordered_groups = sorted(
        grouped.values(),
        key=_friction_priority,
    )
    report["rules"] = [_rule_row(group) for group in ordered_groups]
    report["interventions"] = _interventions(chains)
    report["representative_sequences"] = representative_sequences(chains)
    report["report_classifications"] = (
        ["instrumentation_duplication"] if duplicate_records_removed else []
    )
    return report
