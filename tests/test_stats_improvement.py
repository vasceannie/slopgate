"""Improvement metrics: shared fixtures, evaluator semantics, CLI comparisons."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from slopgate._types import ObjectDict, object_dict, object_list
from slopgate.stats import (
    ComparisonRequest,
    analyze,
    build_improvement,
    resolve_comparison,
)
from slopgate.stats.improvement import (
    parse_result_records,
    semantic_tool_family,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "improvement"
FIXTURE_PATHS = sorted(FIXTURE_DIR.glob("*.json"))

STATES = (
    "resolved",
    "still_failing",
    "no_observed_followup",
    "provenance_changed",
    "evaluation_error",
)


def _strict_entry(
    timestamp: str,
    session: str = "s1",
    rule_id: str | None = None,
    policy: str = "pol-a",
) -> dict[str, object]:
    findings: list[object] = []
    if rule_id:
        findings.append(
            {
                "rule_id": rule_id,
                "decision": "deny",
                "severity": "HIGH",
                "message": f"{rule_id} fired",
                "metadata": {"path": "src/a.py"},
            }
        )
    return {
        "timestamp": timestamp,
        "session_id": session,
        "event_name": "PreToolUse",
        "tool_name": "Write",
        "mutating": True,
        "enforcement_mode": "repo_strict",
        "resolved_repo_root": "/repos/demo",
        "candidate_paths": ["/repos/demo/src/a.py"],
        "languages": ["python"],
        "slopgate_version": "2.1.0",
        "effective_policy_fingerprint": policy,
        "guidance_fingerprint": "gui-a",
        "findings": findings,
        "errors": [],
        "timing": {"evaluation_ms": 10, "rule_engine_ms": 7},
    }


def load_fixture(path: Path) -> tuple[list[dict[str, object]], ObjectDict]:
    payload = object_dict(json.loads(path.read_text(encoding="utf-8")))
    entries: list[dict[str, object]] = [
        object_dict(item)
        for item in object_list(payload.get("entries"))
        if isinstance(item, dict)
    ]
    expected = object_dict(payload.get("expected"))
    assert entries, f"fixture {path.name} must contain entries"
    return entries, expected


def fixture_summary(improvement: ObjectDict) -> ObjectDict:
    """Project the improvement object onto the cross-language fixture contract."""
    headline = object_dict(improvement.get("headline"))
    episodes = object_dict(improvement.get("episodes"))
    legacy = object_dict(improvement.get("legacy_rows"))
    return {
        "authoritative": improvement.get("authoritative"),
        "legacy_rows": legacy.get("count"),
        "episodes": {state: episodes.get(state) for state in STATES},
        "headline": {
            "blocking_per_100_mutations": object_dict(
                headline.get("blocking_per_100_mutations")
            ),
            "first_attempt_clean_rate": object_dict(
                headline.get("first_attempt_clean_rate")
            ),
            "repair_success_rate": object_dict(headline.get("repair_success_rate")),
            "median_repair_attempts": object_dict(
                headline.get("repair_attempts")
            ).get("median"),
            "median_repair_latency_ms": object_dict(
                headline.get("repair_latency_ms")
            ).get("median"),
        },
    }


@pytest.mark.parametrize("path", FIXTURE_PATHS, ids=lambda path: path.stem)
def test_fixture_contract(path: Path) -> None:
    entries, expected = load_fixture(path)

    summary = fixture_summary(build_improvement(entries))

    assert summary == expected, (
        f"fixture {path.stem} must match the canonical evaluator contract"
    )


def test_analyze_preserves_legacy_keys_and_adds_improvement() -> None:
    entries: list[dict[str, object]] = [
        {
            "timestamp": "2026-08-01T12:00:00+00:00",
            "event_name": "PreToolUse",
            "session_id": "real-1",
            "tool_name": "Write",
            "findings": [
                {
                    "rule_id": "GIT-001",
                    "decision": "deny",
                    "severity": "HIGH",
                    "message": "GIT-001 triggered",
                    "metadata": {"path": "src/main.py"},
                }
            ],
        }
    ]

    stats = analyze(entries)

    assert stats["first_time_resolution_rate"] == 1.0, (
        "legacy resolution rate must keep its current formula"
    )
    assert stats["single_deny_scope_rate"] == stats["first_time_resolution_rate"], (
        "single_deny_scope_rate must alias the legacy churn metric"
    )
    improvement = object_dict(stats.get("improvement"))
    assert improvement.get("schema_version") == 1, "improvement object must be versioned"
    assert improvement.get("authoritative") is False, (
        "rows without fingerprints must not be authoritative"
    )


def test_improvement_is_deterministic() -> None:
    entries, _expected = load_fixture(
        FIXTURE_DIR / "write_block_clean_edit_resolved.json"
    )

    first = build_improvement(entries)
    second = build_improvement(entries)

    assert first == second, "identical inputs must produce identical improvement"


def test_still_failing_and_persistence() -> None:
    entries = [
        _strict_entry("2026-08-01T10:00:00+00:00", rule_id="PY-CODE-013"),
        _strict_entry("2026-08-01T10:01:00+00:00", rule_id="PY-CODE-013"),
    ]

    payload = build_improvement(entries)
    episodes = object_dict(payload.get("episodes"))
    assert episodes.get("still_failing") == 1, (
        "repeated denial stays still_failing"
    )


def _persistence_payload() -> ObjectDict:
    payload = build_improvement(
        [
            _strict_entry("2026-08-01T10:00:00+00:00", rule_id="PY-CODE-013"),
            _strict_entry("2026-08-01T10:01:00+00:00", rule_id="PY-CODE-013"),
        ]
    )
    by_rule = object_dict(payload.get("by_rule"))
    rule_entry = object_dict(by_rule.get("PY-CODE-013"))
    return object_dict(rule_entry.get("persistence_rate"))


def test_repeated_denial_persistence_rate() -> None:
    persistence = _persistence_payload()
    assert persistence.get("rate") == 1.0, (
        "persistence must reflect enforcement"
    )


def test_repeated_denial_persistence_denominator() -> None:
    persistence = _persistence_payload()
    assert persistence.get("denominator") == 1, (
        "both follow-ups must be counted"
    )


def test_fixture_sessions_are_filtered() -> None:
    entries: Sequence[object] = [
        {
            "timestamp": "2026-08-01T10:00:00+00:00",
            "session_id": "fixture-run",
            "event_name": "PreToolUse",
            "tool_name": "Write",
            "findings": [],
        }
    ]

    assert parse_result_records(entries) == [], "fixture sessions must be filtered"


@pytest.mark.parametrize(
    ("tool", "event", "expected"),
    [
        ("Write", "PreToolUse", "file_mutation"),
        ("Edit", "PreToolUse", "file_mutation"),
        ("NotebookEdit", "PreToolUse", "file_mutation"),
        ("apply_patch", "PreToolUse", "file_mutation"),
        ("Bash", "PreToolUse", "shell"),
        ("Grep", "PreToolUse", "search"),
        ("WebFetch", "PreToolUse", "web"),
        ("Stop", "Stop", "lifecycle"),
        ("Read", "PreToolUse", "other"),
    ],
)
def test_semantic_tool_families(tool: str, event: str, expected: str) -> None:
    assert semantic_tool_family(tool, event) == expected, (
        f"{tool}/{event} must map to the {expected} family"
    )


def _policy_entries() -> list[dict[str, object]]:
    return [
        _strict_entry("2026-08-01T10:00:00+00:00", session="s-a", policy="pol-a"),
        _strict_entry("2026-08-01T10:01:00+00:00", session="s-b", policy="pol-b"),
    ]


def _resolved_policy_comparison(entries: Sequence[object]) -> ObjectDict:
    request = ComparisonRequest(baseline_policy="pol-a", candidate_policy="pol-b")
    payload, error = resolve_comparison(entries, request)
    assert error is None, f"valid selectors must not error: {error}"
    assert payload is not None, "valid selectors must produce a comparison"
    return payload


def test_comparison_reports_deltas_for_matched_cohorts() -> None:
    payload = _resolved_policy_comparison(_policy_entries())
    aggregate = object_dict(payload.get("aggregate"))
    assert aggregate == {"available": True, "suppression_reason": None}, (
        "matched repo/mode/platform/model facets must allow the aggregate"
    )


def test_comparison_reports_selected_dimension() -> None:
    payload = _resolved_policy_comparison(_policy_entries())
    assert payload.get("dimension") == "policy", "dimension must echo the selector"


def test_comparison_reports_blocking_delta() -> None:
    payload = _resolved_policy_comparison(_policy_entries())
    deltas = object_dict(payload.get("metric_deltas"))
    blocking_delta = object_dict(deltas.get("blocking_per_100_mutations"))
    assert blocking_delta.get("absolute") == 0.0, (
        "identical sides must yield zero blocking-rate delta"
    )


def test_comparison_suppresses_aggregate_on_model_mix() -> None:
    entries = _policy_entries()
    entries[0]["model"] = "model-a"
    entries[1]["model"] = "model-b"
    payload = _resolved_policy_comparison(entries)
    aggregate = object_dict(payload.get("aggregate"))
    assert aggregate.get("available") is False, (
        "differing model facets must suppress the headline aggregate"
    )


def test_comparison_reports_model_confounder() -> None:
    entries = _policy_entries()
    entries[0]["model"] = "model-a"
    entries[1]["model"] = "model-b"
    payload = _resolved_policy_comparison(entries)
    confounding = object_list(payload.get("confounding_dimensions"))
    assert "model" in confounding, (
        "model must be reported as confounding"
    )


def test_comparison_rejects_unknown_fingerprint() -> None:
    request = ComparisonRequest(baseline_policy="pol-a", candidate_policy="ghost")

    payload, error = resolve_comparison(_policy_entries(), request)

    assert payload is None, "unknown fingerprints must not produce a comparison"
    assert error is not None, "unknown fingerprints must report an error"
    assert "not present in trace data" in error


def test_comparison_rejects_incomplete_pair() -> None:
    request = ComparisonRequest(baseline_policy="pol-a")

    payload, error = resolve_comparison(_policy_entries(), request)

    assert payload is None, "incomplete pairs must not produce a comparison"
    assert error is not None, "incomplete pairs must report an error"
    assert "--candidate-policy is required" in error


def test_comparison_cohort_filter_narrows_sides() -> None:
    entries = _policy_entries()
    entries[1]["enforcement_mode"] = "repo_relaxed"
    request = ComparisonRequest(
        baseline_policy="pol-a",
        candidate_policy="pol-b",
        cohorts=("enforcement_mode=repo_strict",),
    )

    _payload, error = resolve_comparison(entries, request)

    assert error == (
        "policy fingerprint not present in trace data: candidate"
    ), "cohort filter must drop relaxed candidate rows entirely"

