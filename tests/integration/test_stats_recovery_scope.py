"""Integration coverage for scoped recovery analysis."""

from __future__ import annotations

from slopgate._types import ObjectDict, object_dict
from slopgate.constants import METADATA_DECISION
from slopgate.stats.recovery.normalization import normalize_entries
from slopgate.stats.recovery.rule_metrics import recovery_report
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


_BATCH = normalize_entries(
    [
        _denial("STRICT-RULE", "repo_strict"),
        _denial("RELAXED-RULE", "repo_relaxed"),
    ]
)


def test_managed_scope_pipeline_excludes_relaxed_recovery() -> None:
    managed_events = scoped_events(_BATCH.events, RecoveryScope.MANAGED)
    report = recovery_report(managed_events, _BATCH.duplicate_records_removed)
    summary = object_dict(report.get("summary"))

    assert summary.get("chains") == 1, (
        "Normalization, scope selection, and recovery aggregation must remain isolated"
    )
