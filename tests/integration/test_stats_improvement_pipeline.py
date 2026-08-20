"""Integration and property contracts for improvement trace evaluation."""

from __future__ import annotations

from datetime import datetime

from hypothesis import given, strategies

from slopgate.stats.improvement import (
    ComparisonRequest,
    ComparisonSpec,
    EpisodeEvaluation,
    RepairEpisode,
    ResultRecord,
    apply_cohort_filters,
    build_comparison,
    evaluate_episodes,
    evaluate_first_observed,
    normalize_target_path,
    parse_result_records,
    resolve_comparison,
    semantic_tool_family,
)
from slopgate.stats.improvement.scope_model import (
    normalized_path_set,
    optional_str,
    parse_result_record,
    parse_timestamp,
    timestamp_key,
)


def _result(timestamp: str, policy: str, rule_id: str | None) -> dict[str, object]:
    findings: list[object] = []
    if rule_id is not None:
        findings.append(
            {
                "rule_id": rule_id,
                "decision": "deny",
                "metadata": {"path": "src/a.py"},
            }
        )
    return {
        "timestamp": timestamp,
        "session_id": f"session-{policy}",
        "event_name": "PreToolUse",
        "tool_name": "Write",
        "mutating": True,
        "enforcement_mode": "repo_strict",
        "resolved_repo_root": "/repo",
        "candidate_paths": ["/repo/src/a.py"],
        "languages": ["python"],
        "slopgate_version": "2.1.0",
        "effective_policy_fingerprint": policy,
        "guidance_fingerprint": "guidance-a",
        "findings": findings,
        "errors": [],
    }


def test_integration_result_pipeline_builds_typed_episode() -> None:
    entries = [
        _result("2026-08-01T10:00:00+00:00", "policy-a", "PY-CODE-013"),
        _result("2026-08-01T10:01:00+00:00", "policy-a", None),
    ]

    records = parse_result_records(entries)
    evaluation = evaluate_episodes(records)

    assert isinstance(records[0], ResultRecord), "parser must return typed records"
    assert isinstance(evaluation, EpisodeEvaluation), "pipeline must return typed evaluation"
    assert isinstance(evaluation.episodes[0], RepairEpisode), "block must anchor an episode"
    assert evaluate_first_observed(records) == evaluation.first_observed, (
        "standalone scope evaluation must match the episode pipeline"
    )


def test_integration_comparison_filters_and_builds_matching_sides() -> None:
    entries = [
        _result("2026-08-01T10:00:00+00:00", "policy-a", None),
        _result("2026-08-01T10:01:00+00:00", "policy-b", None),
    ]
    records = parse_result_records(entries)
    filtered = apply_cohort_filters(records, (("enforcement_mode", "repo_strict"),))
    spec = ComparisonSpec(
        dimension="policy",
        baseline="policy-a",
        candidate="policy-b",
        cohorts=(),
    )

    payload, error = build_comparison(filtered, spec)

    assert error is None, f"matched integration rows must compare: {error}"
    assert payload is not None and payload["dimension"] == "policy", (
        "comparison must preserve the selected intervention"
    )


def test_integration_comparison_excludes_legacy_rows_from_cohorts() -> None:
    legacy = _result("2026-08-01T10:00:00+00:00", "policy-a", None)
    del legacy["slopgate_version"]
    current = _result("2026-08-01T10:01:00+00:00", "policy-b", None)

    spec = ComparisonSpec(
        dimension="policy",
        baseline="policy-a",
        candidate="policy-b",
        cohorts=(),
    )
    payload, error = build_comparison(
        parse_result_records([legacy, current]), spec
    )

    assert payload is None, "legacy rows must not enter comparison cohorts"
    assert error == "policy fingerprint not present in trace data: baseline"


def test_integration_multi_rule_paths_are_rule_local() -> None:
    blocked = _result("2026-08-01T10:00:00+00:00", "policy-a", None)
    blocked["findings"] = [
        {"rule_id": "RULE-A", "decision": "deny", "metadata": {"path": "src/a.py"}},
        {"rule_id": "RULE-B", "decision": "deny", "metadata": {"path": "src/b.py"}},
    ]
    clean_a = _result("2026-08-01T10:01:00+00:00", "policy-a", None)
    clean_a["candidate_paths"] = ["/repo/src/a.py"]

    evaluation = evaluate_episodes(parse_result_records([blocked, clean_a]))
    states = {episode.rule_id: episode.state for episode in evaluation.episodes}

    assert states == {
        "RULE-A": "resolved",
        "RULE-B": "no_observed_followup",
    }, "a follow-up must resolve only the rule sharing its finding path"


def test_integration_comparison_supports_rule_and_confidence_cohorts() -> None:
    entries = [
        _result("2026-08-01T10:00:00+00:00", "policy-a", "RULE-A"),
        _result("2026-08-01T10:01:00+00:00", "policy-b", "RULE-A"),
    ]
    request = ComparisonRequest(
        baseline_policy="policy-a",
        candidate_policy="policy-b",
        cohorts=("rule=RULE-A", "scope_confidence=high"),
    )

    payload, error = resolve_comparison(entries, request)

    assert error is None, "rule and confidence cohorts must be accepted"
    assert payload is not None and payload["dimension"] == "policy", (
        "accepted cohorts must produce the selected comparison"
    )


def test_integration_scope_path_helpers_preserve_identity() -> None:
    assert normalize_target_path("/repo/src/../src/a.py", "/repo") == "src/a.py"
    assert normalized_path_set(["/repo/src/a.py", "/repo/src/./a.py"], "/repo") == (
        "src/a.py",
    )


def test_integration_scope_value_helpers_parse_record() -> None:
    entry = _result("2026-08-01T10:00:00+00:00", "policy-a", None)
    record = parse_result_record(entry, 0)

    assert record is not None, "valid result input must parse"
    assert optional_str("policy-a") == "policy-a"
    assert timestamp_key(entry["timestamp"])[0] == 0


@given(strategies.text())
def test_parse_timestamp_property_never_raises(raw: str) -> None:
    parsed = parse_timestamp(raw)
    assert parsed is None or isinstance(parsed, datetime), (
        "timestamp parser must return datetime or explicit failure"
    )


@given(strategies.text(), strategies.text())
def test_semantic_tool_family_property_is_bounded(tool: str, event: str) -> None:
    family = semantic_tool_family(tool, event)
    assert family in {"file_mutation", "shell", "search", "web", "lifecycle", "other"}


@given(
    strategies.lists(
        strategies.one_of(strategies.none(), strategies.integers(), strategies.text()),
        max_size=12,
    )
)
def test_parse_result_records_property_accepts_untrusted_rows(entries: list[object]) -> None:
    assert parse_result_records(entries) == [], (
        "non-mapping rows must be ignored at the trace boundary"
    )


@given(
    strategies.text(min_size=1).filter(
        lambda value: value not in {"policy-a", "policy-b"}
    )
)
def test_resolve_comparison_property_rejects_unknown_policy(candidate: str) -> None:
    entries = [
        _result("2026-08-01T10:00:00+00:00", "policy-a", None),
        _result("2026-08-01T10:01:00+00:00", "policy-b", None),
    ]
    request = ComparisonRequest(
        baseline_policy="policy-a",
        candidate_policy=candidate,
    )

    payload, error = resolve_comparison(entries, request)

    assert payload is None, "unknown candidate policy must not produce a comparison"
    assert error == "policy fingerprint not present in trace data: candidate"
