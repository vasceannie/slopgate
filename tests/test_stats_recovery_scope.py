"""Scope isolation contracts for actionable recovery reporting."""

from __future__ import annotations

import pytest
from hypothesis import given, strategies

from slopgate._types import ObjectDict, object_dict
from slopgate.cli.parsers import build_parser
from slopgate.constants import METADATA_DECISION
from slopgate.stats import analyze
from slopgate.stats.recovery.normalization import normalize_entries
from slopgate.stats.recovery.scopes import RecoveryScope, scoped_events


def _denial(evaluation_id: str, mode: str) -> ObjectDict:
    return {
        "timestamp": "2026-07-14T12:00:00+00:00",
        "trace_schema_version": 2,
        "evaluation_id": evaluation_id,
        "correlation_confidence": "inferred",
        "event_name": "PreToolUse",
        "event_outcome": "blocked_pre_tool",
        "tool_outcome": "unknown",
        "session_id": evaluation_id,
        "tool_name": "Edit",
        "candidate_paths": ["src/app.py"],
        "attempt_fingerprint": evaluation_id,
        "resolved_repo_root": f"/{mode}",
        "enforcement_mode": mode,
        "platform_capability": "full",
        "rule_response_version": "1",
        "intervention_tags": [],
        "repair_plan_state": "none",
        "findings": [
            {
                "rule_id": evaluation_id,
                METADATA_DECISION: "deny",
                "severity": "HIGH",
                "message": evaluation_id,
                "metadata": {"path": "src/app.py"},
            }
        ],
        "errors": [],
    }


_STRICT = _denial("STRICT-RULE", "repo_strict")
_RELAXED = _denial("RELAXED-RULE", "repo_relaxed")
_GLOBAL = _denial("GLOBAL-RULE", "outside_repo")
_ALL_RECOVERY = object_dict(
    analyze(
        [_STRICT, _RELAXED, _GLOBAL],
        scope=RecoveryScope.ALL,
    ).get("recovery")
)
_ALL_REPORTS = object_dict(_ALL_RECOVERY.get("scope_reports"))
_ALL_EVENTS = normalize_entries([_STRICT, _RELAXED, _GLOBAL]).events
_EXPECTED_MODES = {
    RecoveryScope.MANAGED: {"repo_strict"},
    RecoveryScope.RELAXED: {"repo_relaxed"},
    RecoveryScope.GLOBAL: {"outside_repo"},
    RecoveryScope.ALL: {"repo_strict", "repo_relaxed", "outside_repo"},
}


def test_analyze_defaults_recovery_to_managed_repositories() -> None:
    recovery = object_dict(analyze([_STRICT, _RELAXED, _GLOBAL]).get("recovery"))
    summary = object_dict(recovery.get("summary"))

    assert (recovery.get("scope"), summary.get("chains")) == ("managed", 1), (
        "Default recovery analytics must isolate repo_strict activity"
    )


def test_analyze_selects_relaxed_recovery_scope() -> None:
    recovery = object_dict(
        analyze(
            [_STRICT, _RELAXED, _GLOBAL],
            scope=RecoveryScope.RELAXED,
        ).get("recovery")
    )
    summary = object_dict(recovery.get("summary"))

    assert (recovery.get("scope"), summary.get("chains")) == ("relaxed", 1), (
        "Explicit relaxed scope must exclude strict and global events"
    )


@pytest.mark.parametrize("scope_name", ["managed", "relaxed", "global"])
def test_all_scope_keeps_recovery_reports_separate(scope_name: str) -> None:
    report = object_dict(_ALL_REPORTS.get(scope_name))
    summary = object_dict(report.get("summary"))

    assert summary.get("chains") == 1, (
        "All scope must render separate funnels rather than a blended chain count"
    )


def test_stats_parser_accepts_recovery_scope() -> None:
    args = build_parser().parse_args(["stats", "--scope", "global"])

    assert args.scope == "global", "CLI must expose explicit recovery scope selection"


@given(strategies.sampled_from(tuple(RecoveryScope)))
def test_scoped_events_returns_only_allowed_modes(scope: RecoveryScope) -> None:
    selected = scoped_events(_ALL_EVENTS, scope)

    assert {event.enforcement_mode for event in selected} == _EXPECTED_MODES[scope], (
        "Scope selection must preserve exact enforcement-mode boundaries"
    )
