"""Legacy denial-churn compatibility tests with honest metric names."""

from __future__ import annotations

import json
from typing import Final

from slopgate._types import ObjectDict, object_list
from slopgate.constants import METADATA_DECISION
from slopgate.stats import analyze
from tests.support import (
    StatsResultSpec,
    nested_output,
    pair_counts,
    stats_result_entry,
)

QUALITY_BLOCK_ENTRY: Final = stats_result_entry(
    StatsResultSpec(rule_id="QUALITY-LINT-001", decision="block")
)
REPEATED_CODE_ENTRY: Final = stats_result_entry(StatsResultSpec(rule_id="PY-CODE-009"))
SINGLE_CODE_ENTRY: Final = stats_result_entry(
    StatsResultSpec(rule_id="PY-CODE-010", session_id="s2")
)


def _legacy_churn(stats: ObjectDict) -> ObjectDict:
    legacy_metrics = nested_output(stats, "legacy_metrics")
    return nested_output(legacy_metrics, "legacy_churn")


def _blocking_metric_projection(stats: ObjectDict) -> dict[str, int | None]:
    churn = _legacy_churn(stats)
    return {
        "top_rules_enforced": pair_counts(stats, "top_rules_enforced").get(
            "QUALITY-LINT-001"
        ),
        "top_rules_denied": pair_counts(stats, "top_rules_denied").get(
            "QUALITY-LINT-001"
        ),
        "top_files_denied": pair_counts(stats, "top_files_denied").get("src/main.py"),
        "session_rule_denial_frequency": pair_counts(
            churn,
            "session_rule_denial_frequency",
        ).get("QUALITY-LINT-001 (session-1)"),
        "repeated_deny_key_count_by_rule": pair_counts(
            churn,
            "repeated_deny_key_count_by_rule",
        ).get("QUALITY-LINT-001"),
        "top_looping_files": pair_counts(churn, "top_looping_files").get(
            "file:target-1"
        ),
    }


def test_session_rule_denial_frequency_detects_repeated_keys() -> None:
    stats = analyze([stats_result_entry()] * 3)
    retries = object_list(_legacy_churn(stats).get("session_rule_denial_frequency"))

    assert retries == [("GIT-001 (session-1)", 3)], (
        "Repeated denials must remain available as frequency, not resolution"
    )


def test_blocking_findings_feed_honest_churn_metrics() -> None:
    stats = analyze([QUALITY_BLOCK_ENTRY, QUALITY_BLOCK_ENTRY])

    assert _blocking_metric_projection(stats) == {
        "top_rules_enforced": 2,
        "top_rules_denied": 2,
        "top_files_denied": 2,
        "session_rule_denial_frequency": 2,
        "repeated_deny_key_count_by_rule": 1,
        "top_looping_files": 2,
    }, "Blocking findings must feed counts without claiming recovery"


def test_single_occurrence_ratio_describes_deny_keys() -> None:
    stats = analyze([REPEATED_CODE_ENTRY, REPEATED_CODE_ENTRY, SINGLE_CODE_ENTRY])
    ratio = _legacy_churn(stats).get("single_occurrence_deny_key_ratio")

    assert ratio == 0.5, "One of two denial keys should be a single occurrence"


def test_pathless_rules_remain_separate_from_file_targets() -> None:
    entry = stats_result_entry(StatsResultSpec(rule_id="SHELL-001"))
    entry["findings"] = [
        {
            "rule_id": "SHELL-001",
            METADATA_DECISION: "deny",
            "severity": "HIGH",
            "message": "No shell",
            "metadata": {},
        }
    ]

    pathless = pair_counts(
        _legacy_churn(analyze([entry, entry])),
        "top_pathless_loop_rules",
    )

    assert pathless.get("SHELL-001", 0) >= 1, (
        "Pathless findings must not be mixed into file-backed churn"
    )


def test_legacy_churn_redacts_raw_command_repository_and_session_values() -> None:
    secret_command = "deploy --token top-secret-token"
    secret_repository = "private-repository-root"
    secret_session = "sensitive-session-id"
    entry = stats_result_entry(StatsResultSpec(rule_id="SHELL-001"))
    updates: ObjectDict = {
        "candidate_paths": [],
        "command": secret_command,
        "resolved_repo_root": secret_repository,
        "session_id": secret_session,
        "findings": [
            {
                "rule_id": "SHELL-001",
                METADATA_DECISION: "deny",
                "severity": "HIGH",
                "message": "No shell",
                "metadata": {},
            }
        ],
    }
    entry.update(updates)

    serialized = json.dumps(_legacy_churn(analyze([entry, dict(entry)])))

    assert not any(
        value in serialized
        for value in (secret_command, secret_repository, secret_session)
    ), "Deprecated churn output must use opaque target and session labels"
