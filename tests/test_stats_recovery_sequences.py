"""Representative recovery sequence and redaction contracts."""

from __future__ import annotations

import json

from hypothesis import given, strategies

from slopgate._types import ObjectDict, object_list
from slopgate.constants import METADATA_DECISION
from slopgate.stats import analyze
from slopgate.stats.recovery.chains import build_chains
from slopgate.stats.recovery.normalization import normalize_entries
from slopgate.stats.recovery.sequences import representative_sequences

_SECRET = "private-source-content"
_DENIAL: ObjectDict = {
    "timestamp": "2026-07-14T12:00:00+00:00",
    "trace_schema_version": 2,
    "evaluation_id": "deny-1",
    "correlation_confidence": "inferred",
    "event_name": "PreToolUse",
    "event_outcome": "blocked_pre_tool",
    "tool_outcome": "unknown",
    "session_id": "session-1",
    "tool_name": "Edit",
    "candidate_paths": ["src/app.py"],
    "attempt_fingerprint": "same",
    "resolved_repo_root": "/repo",
    "enforcement_mode": "repo_strict",
    "platform_capability": "full",
    "rule_response_version": "1",
    "intervention_tags": ["repair-plan-requested"],
    "repair_plan_state": "requested",
    "tool_input": {"content": _SECRET},
    "tool_output": _SECRET,
    "findings": [
        {
            "rule_id": "RULE-001",
            METADATA_DECISION: "deny",
            "severity": "HIGH",
            "message": _SECRET,
            "metadata": {"path": "src/app.py"},
        }
    ],
    "errors": [],
}
_SUCCESS: ObjectDict = {
    **_DENIAL,
    "timestamp": "2026-07-14T12:01:00+00:00",
    "evaluation_id": "success-1",
    "event_name": "PostToolUse",
    "event_outcome": "passed_clean",
    "tool_outcome": "success",
    "findings": [],
}
_BATCH = normalize_entries([_DENIAL, _SUCCESS])
_CHAINS = build_chains(_BATCH.events)
_SEQUENCES = representative_sequences(_CHAINS)
_SENSITIVE_VALUES = (
    "sensitive-session-id",
    "/home/alice/customer-private",
    "deploy --token top-secret-token",
    "top-secret-token",
)
_SENSITIVE_DENIAL: ObjectDict = {
    **_DENIAL,
    "session_id": _SENSITIVE_VALUES[0],
    "candidate_paths": [],
    "resolved_repo_root": _SENSITIVE_VALUES[1],
    "command": _SENSITIVE_VALUES[2],
    "intervention_tags": [],
    "findings": [
        {
            "rule_id": "RULE-001",
            METADATA_DECISION: "deny",
            "severity": "HIGH",
            "message": "blocked",
            "metadata": {},
        }
    ],
}
_SENSITIVE_TERMINAL: ObjectDict = {
    **_SENSITIVE_DENIAL,
    "timestamp": "2026-07-14T12:01:00+00:00",
    "evaluation_id": "terminal-1",
    "event_name": "Stop",
    "event_outcome": "passed_clean",
    "findings": [],
}
_SENSITIVE_SEQUENCES = representative_sequences(
    build_chains(normalize_entries([_SENSITIVE_DENIAL, _SENSITIVE_TERMINAL]).events)
)


def test_representative_sequences_select_observed_archetypes() -> None:
    archetypes = {sequence.get("archetype") for sequence in _SEQUENCES}

    assert archetypes == {"unchanged_retry_loop", "recovery_after_intervention"}, (
        "Sequence selection must expose each observed friction archetype once"
    )


def test_representative_sequences_redact_raw_trace_content() -> None:
    serialized = json.dumps(_SEQUENCES)

    assert (
        _SECRET not in serialized
        and "tool_input" not in serialized
        and "tool_output" not in serialized
        and "message" not in serialized
    ), "Representative evidence must exclude raw tool and finding content"


def test_representative_sequences_redact_command_paths_and_sessions() -> None:
    serialized = json.dumps(_SENSITIVE_SEQUENCES)

    assert not any(value in serialized for value in _SENSITIVE_VALUES), (
        "Representative evidence must not expose raw session, repository, or command targets"
    )


def test_analyze_projects_representative_sequences_at_top_level() -> None:
    sequences = object_list(
        analyze([_DENIAL, _SUCCESS]).get("representative_sequences")
    )

    assert len(sequences) == 2, (
        "The compatibility analyzer must expose selected sequences at the report surface"
    )


@given(strategies.integers(min_value=0, max_value=20))
def test_representative_sequences_never_duplicate_archetypes(repeats: int) -> None:
    sequences = representative_sequences(_CHAINS * repeats)
    archetypes = [sequence.get("archetype") for sequence in sequences]

    assert len(archetypes) == len(set(archetypes)), (
        "Representative selection must emit at most one sequence per archetype"
    )
