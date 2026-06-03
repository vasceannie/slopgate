from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies

from vibeforcer.stats import analyze, load_entries, print_report, run_stats


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
    log_path = tmp_path / "events.jsonl"
    log_path.write_text(
        '{"timestamp":"2026-06-03T00:00:00+00:00","event_name":"fresh"}\n'
        '{"timestamp":"2020-01-01T00:00:00+00:00","event_name":"stale"}\n',
        encoding="utf-8",
    )

    assert load_entries(log_path, days=1) == [
        {"timestamp": "2026-06-03T00:00:00+00:00", "event_name": "fresh"}
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


def test_print_report_renders_analyzed_stats(capsys: pytest.CaptureFixture[str]) -> None:
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
    assert "VIBEFORCER HOOK ACTIVITY REPORT" in output
    assert "Total hook events: 1" in output
    assert "deny" in output


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
