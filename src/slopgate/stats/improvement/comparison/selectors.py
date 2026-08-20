"""Comparison selectors: request validation and cohort filter parsing."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from slopgate._types import ObjectDict
from slopgate.constants import PLATFORM_KEY

from ..episodes import parse_result_records

COMPARISON_DIMENSIONS = ("policy", "guidance")

ENTRY_COHORT_FIELDS = {
    "repo": "repo_root",
    "enforcement_mode": "enforcement_mode",
    PLATFORM_KEY: PLATFORM_KEY,
    "capability": "platform_capability",
    "model": "model",
    "provider": "provider",
    "version": "slopgate_version",
    "policy": "policy_fingerprint",
    "guidance": "guidance_fingerprint",
}
LANGUAGE_COHORT = "language"
RULE_COHORT = "rule"
SCOPE_CONFIDENCE_COHORT = "scope_confidence"


@dataclass(frozen=True, slots=True)
class ComparisonSpec:
    """One complete baseline/candidate selector pair plus cohort filters."""

    dimension: str
    baseline: str
    candidate: str
    cohorts: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ComparisonRequest:
    """Raw CLI comparison selectors before validation."""

    baseline_policy: str | None = None
    candidate_policy: str | None = None
    baseline_guidance: str | None = None
    candidate_guidance: str | None = None
    cohorts: tuple[str, ...] = ()


def resolve_comparison(
    entries: Sequence[object], request: ComparisonRequest
) -> tuple[ObjectDict | None, str | None]:
    """Validate selectors and build the comparison, or explain the error."""
    error = _validate_request(request)
    if error is not None:
        return None, error
    cohort_filters, cohort_errors = parse_cohort_filters(request.cohorts)
    if cohort_errors:
        return None, "; ".join(cohort_errors)
    selected = _selected_pair(request)
    if selected is None:
        return None, "comparison selectors are incomplete"
    dimension, baseline, candidate = selected
    spec = ComparisonSpec(
        dimension=dimension,
        baseline=baseline,
        candidate=candidate,
        cohorts=tuple(cohort_filters),
    )
    records = parse_result_records(entries)
    from .evaluate import build_comparison

    return build_comparison(records, spec)


def parse_cohort_filters(
    raw: Sequence[str],
) -> tuple[list[tuple[str, str]], list[str]]:
    """Parse ``dimension=value`` strings; return valid pairs plus errors."""
    valid: list[tuple[str, str]] = []
    errors: list[str] = []
    for item in raw:
        name, separator, value = item.partition("=")
        dimension = name.strip()
        if not separator or not value.strip():
            errors.append(f"cohort filter must be dimension=value: {item}")
            continue
        if dimension not in ENTRY_COHORT_FIELDS and dimension not in {
            LANGUAGE_COHORT,
            RULE_COHORT,
            SCOPE_CONFIDENCE_COHORT,
        }:
            errors.append(
                f"unknown cohort dimension: {dimension} "
                f"(expected one of {', '.join((*ENTRY_COHORT_FIELDS, LANGUAGE_COHORT))})"
            )
            continue
        valid.append((dimension, value.strip()))
    return valid, errors


def _validate_request(request: ComparisonRequest) -> str | None:
    if request.baseline_policy and not request.candidate_policy:
        return "--candidate-policy is required with --baseline-policy"
    if request.candidate_policy and not request.baseline_policy:
        return "--baseline-policy is required with --candidate-policy"
    if request.baseline_guidance and not request.candidate_guidance:
        return "--candidate-guidance is required with --baseline-guidance"
    if request.candidate_guidance and not request.baseline_guidance:
        return "--baseline-guidance is required with --candidate-guidance"
    if request.baseline_policy and request.baseline_guidance:
        return "select either a policy pair or a guidance pair, not both"
    if _selected_pair(request) is None:
        return (
            "comparison requires one complete pair: --baseline-policy with"
            " --candidate-policy, or --baseline-guidance with"
            " --candidate-guidance"
        )
    return None


def _selected_pair(
    request: ComparisonRequest,
) -> tuple[str, str, str] | None:
    if request.baseline_policy and request.candidate_policy:
        return ("policy", request.baseline_policy, request.candidate_policy)
    if request.baseline_guidance and request.candidate_guidance:
        return ("guidance", request.baseline_guidance, request.candidate_guidance)
    return None
