from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies

from slopgate._types import ObjectDict
from slopgate.stats import analyze, load_entries, print_report, run_stats


_RECOVERY_REPORT: ObjectDict = {
    "summary": {"chains": 2, "recovered": 1, "abandoned": 0, "open_censored": 1},
    "rates": {
        "first_retry_rule_clearance": {
            "numerator": 1,
            "denominator": 2,
            "percentage": 50.0,
        },
        "first_retry_operation_success": {
            "numerator": 0,
            "denominator": 0,
            "percentage": None,
        },
    },
    "rules": [
        {
            "label": "RULE-001",
            "chains": 2,
            "primary_classification": "insufficient_telemetry",
            "first_retry_operation_success": {
                "numerator": 0,
                "denominator": 0,
                "percentage": None,
            },
            "unchanged_first_retry": {
                "numerator": 1,
                "denominator": 2,
                "percentage": 50.0,
            },
            "eventual_recovery": {
                "numerator": 1,
                "denominator": 1,
                "percentage": 100.0,
            },
            "abandoned": 0,
            "open_censored": 1,
            "sessions": 1,
        }
    ],
    "interventions": [],
    "report_classifications": [],
}


def test_load_entries_skips_invalid_json_lines(tmp_path: Path) -> None:
    log_path = tmp_path / "events.jsonl"
    log_path.write_text(
        '{"timestamp":"2026-06-03T00:00:00+00:00","event_name":"PreToolUse"}\n'
        "{not-json\n\n",
        encoding="utf-8",
    )

    assert load_entries(log_path, days=None) == [
        {"timestamp": "2026-06-03T00:00:00+00:00", "event_name": "PreToolUse"}
    ]


def test_load_entries_filters_events_older_than_day_window(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    fresh_ts = now.isoformat()
    stale_ts = (now - timedelta(days=30)).isoformat()
    log_path = tmp_path / "events.jsonl"
    log_path.write_text(
        f'{{"timestamp":"{fresh_ts}","event_name":"fresh"}}\n'
        f'{{"timestamp":"{stale_ts}","event_name":"stale"}}\n',
        encoding="utf-8",
    )

    assert load_entries(log_path, days=1) == [
        {"timestamp": fresh_ts, "event_name": "fresh"}
    ]


@given(strategies.lists(strategies.text(alphabet="abc123", max_size=12), max_size=5))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_load_entries_ignores_malformed_json_lines(
    tmp_path: Path,
    fragments: list[str],
) -> None:
    log_path = tmp_path / "events.jsonl"
    log_path.write_text(
        "\n".join(f"not-json:{fragment}" for fragment in fragments),
        encoding="utf-8",
    )

    assert load_entries(log_path, days=None) == []


def test_print_report_renders_analyzed_stats(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stats = analyze(
        [
            {
                "timestamp": "2026-06-03T00:00:00+00:00",
                "event_name": "PreToolUse",
                "session_id": "session-1",
                "decision": "deny",
                "rule_id": "RULE-001",
                "severity": "HIGH",
            }
        ]
    )

    print_report(stats)

    output = capsys.readouterr().out
    assert "SLOPGATE HOOK ACTIVITY REPORT" in output
    assert "Total hook events: 1" in output
    assert "deny" in output


def test_print_report_uses_honest_event_and_finding_units(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stats = analyze(
        [
            {
                "timestamp": "2026-06-03T00:00:00+00:00",
                "event_name": "PreToolUse",
                "session_id": "session-1",
                "findings": [
                    {
                        "rule_id": "RULE-001",
                        "decision": "deny",
                        "severity": "HIGH",
                        "message": "Denied",
                    }
                ],
            }
        ]
    )

    print_report(stats)
    output = capsys.readouterr().out

    assert (
        "Event Outcomes" in output,
        "Finding Decisions" in output,
        "100.0% (1/1)" in output,
        "First-time resolution" not in output,
        "retries before resolution" not in output,
    ) == (True, True, True, True, True), (
        "Human report must show unit-safe fractions without false recovery wording"
    )


def test_print_report_renders_recovery_evidence_with_explicit_units(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stats = analyze([])
    stats["recovery"] = _RECOVERY_REPORT

    print_report(stats)
    output = capsys.readouterr().out

    assert (
        "Recovery Chains" in output,
        "50.0% (1/2)" in output,
        "1st retry operation success: —" in output,
        "RULE-001" in output,
        "insufficient_telemetry" in output,
    ) == (True, True, True, True, True), (
        "Recovery reporting must preserve explicit fractions and unavailable values"
    )


def test_run_stats_outputs_json_report_for_existing_log(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    log_path = tmp_path / "events.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-06-03T00:00:00+00:00",
                "event_name": "PostToolUse",
                "session_id": "session-2",
                "decision": "allow",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_stats(str(log_path), as_json=True)
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["total_events"] == 1
    assert payload["by_event"] == [["PostToolUse", 1]]


def test_run_stats_reports_missing_log(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_path = tmp_path / "missing.jsonl"

    result = run_stats(str(missing_path))

    assert result == 1
    assert str(missing_path) in capsys.readouterr().err
