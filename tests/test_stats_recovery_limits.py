"""Bounded recovery analytics and self-test filtering contracts."""

from __future__ import annotations

from slopgate._types import ObjectDict
from slopgate.constants import METADATA_DECISION
from slopgate.stats.recovery.chains import build_chains
from slopgate.stats.recovery.normalization import normalize_entries


def _oversized_denial() -> ObjectDict:
    return {
        "timestamp": "2026-07-14T12:00:00+00:00",
        "trace_schema_version": 2,
        "evaluation_id": "oversized-denial",
        "correlation_confidence": "inferred",
        "event_name": "PreToolUse",
        "event_outcome": "blocked_pre_tool",
        "tool_outcome": "unknown",
        "session_id": "session-1",
        "tool_name": "Edit",
        "candidate_paths": [f"src/path-{index}.py" for index in range(33)],
        "attempt_fingerprint": "fingerprint-1",
        "resolved_repo_root": "/repo",
        "enforcement_mode": "repo_strict",
        "platform_capability": "full",
        "rule_response_version": "1",
        "intervention_tags": [],
        "repair_plan_state": "none",
        "findings": [
            {
                "rule_id": "QUALITY-LINT-001",
                METADATA_DECISION: "deny",
                "severity": "HIGH",
                "message": "Quality gate failed",
                "metadata": {
                    "failing_collectors": [f"collector-{index}" for index in range(17)]
                },
            }
            for _index in range(65)
        ],
        "errors": [],
    }


def test_normalize_entries_excludes_self_test_sessions() -> None:
    entry = _oversized_denial()
    entry["session_id"] = "self-test-opencode-GIT-001"

    batch = normalize_entries([entry])

    assert (batch.events, batch.fixture_filtered) == ((), 1), (
        "Self-test traces must not affect recovery analytics"
    )


def test_normalize_entries_caps_recovery_input_dimensions() -> None:
    event = normalize_entries([_oversized_denial()]).events[0]

    assert (len(event.candidate_paths), len(event.distinct_findings())) == (32, 64), (
        "Recovery normalization must cap candidate paths and source findings"
    )
    assert len(event.findings) == 64 * 16, (
        "Each retained quality finding must cap collector variants at sixteen"
    )


def test_build_chains_caps_new_chains_per_event() -> None:
    event = normalize_entries([_oversized_denial()]).events[0]

    chains = build_chains((event,))

    assert len(chains) == 256, (
        "One trace record must not create more than 256 recovery chains"
    )
