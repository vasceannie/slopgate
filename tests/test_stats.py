"""Unit tests for stats.analyze() and related functions."""

from __future__ import annotations

from datetime import datetime, timezone

from slopgate._types import ObjectDict, object_dict, object_list
from slopgate.stats import analyze, parse_timestamp
from tests.support import (
    StatsResultSpec,
    nested_output,
    pair_counts,
    stats_result_entry,
)


def string_list(mapping: ObjectDict, key: str) -> list[str]:
    return [value for value in object_list(mapping.get(key)) if isinstance(value, str)]


class TestParseTimestamp:
    def test_none_cutoff_never_skips(self) -> None:
        assert not parse_timestamp("2026-01-01T00:00:00+00:00", None), (
            "None cutoff must not skip"
        )

    def test_before_cutoff_skips(self) -> None:
        cutoff = datetime(2026, 3, 1, tzinfo=timezone.utc)
        assert parse_timestamp("2026-02-01T00:00:00+00:00", cutoff), (
            "entry before cutoff must be skipped"
        )

    def test_after_cutoff_keeps(self) -> None:
        cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert not parse_timestamp("2026-06-01T00:00:00+00:00", cutoff), (
            "entry after cutoff must be kept"
        )

    def test_invalid_timestamp_keeps(self) -> None:
        cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert not parse_timestamp("not-a-date", cutoff), (
            "invalid timestamp must not be skipped"
        )


class TestAnalyze:
    def test_counts_deny_decision(self) -> None:
        stats = analyze([stats_result_entry()])
        decisions = pair_counts(stats, "by_decision")
        assert decisions.get("deny") == 1, "deny count must be 1"

    def test_context_only_not_counted_as_allow(self) -> None:
        entry = stats_result_entry(StatsResultSpec(decision="context"))
        stats = analyze([entry])
        decisions = pair_counts(stats, "by_decision")
        assert decisions.get("context", 0) == 1, (
            "context-only findings must be counted as context"
        )
        assert decisions.get("allow", 0) == 0, (
            "context-only must not inflate allow count"
        )

    def test_legacy_no_findings_remain_unknown_without_allow_finding(self) -> None:
        entry: ObjectDict = {
            "timestamp": "2026-04-01T12:00:00+00:00",
            "event_name": "PreToolUse",
            "session_id": "s1",
            "tool_name": "Read",
            "findings": [],
        }
        stats = analyze([entry])
        outcomes = pair_counts(nested_output(stats, "event_outcomes"), "counts")
        decisions = pair_counts(nested_output(stats, "finding_decisions"), "counts")
        assert (outcomes.get("unknown"), decisions.get("allow", 0)) == (1, 0), (
            "Legacy empty findings must remain unknown and create no synthetic allow finding"
        )

    def test_fixture_sessions_filtered(self) -> None:
        entry = stats_result_entry(StatsResultSpec(session_id="fixture-abc"))
        stats = analyze([entry])
        assert stats["fixture_filtered"] == 1, "fixture sessions must be filtered"

    def test_self_test_filtering_exposes_raw_and_analyzed_event_counts(self) -> None:
        fixture_entry = stats_result_entry(StatsResultSpec(session_id="fixture-abc"))
        real_entry = stats_result_entry(StatsResultSpec(session_id="real-session"))

        stats = analyze([fixture_entry, real_entry])

        assert stats["raw_total_events"] == 2
        assert stats["analyzed_events"] == 1
        assert stats["total_events"] == 1
        decisions = pair_counts(stats, "by_decision")
        assert decisions.get("deny") == 1

    def test_daily_counts(self) -> None:
        stats = analyze([stats_result_entry()])
        daily = pair_counts(stats, "daily_counts")
        assert "2026-04-01" in daily, "daily count must include the entry date"

    def test_rule_examples_capped_at_three(self) -> None:
        entries = [stats_result_entry()] * 5
        stats = analyze(entries)
        examples = object_dict(stats.get("rule_examples"))
        assert len(string_list(examples, "GIT-001")) <= 3, (
            "rule examples must be capped at 3"
        )

    def _mixed_enrichment_stats(self) -> ObjectDict:
        noisy_context = [
            stats_result_entry(
                StatsResultSpec(
                    rule_id="ENRICHMENT",
                    decision="context",
                    session_id=f"ctx-{idx}",
                )
            )
            for idx in range(4)
        ]
        metrics = [
            stats_result_entry(
                StatsResultSpec(
                    rule_id="_ENRICHMENT_METRICS",
                    decision="info",
                    session_id=f"met-{idx}",
                )
            )
            for idx in range(3)
        ]
        enforced = [
            stats_result_entry(
                StatsResultSpec(
                    rule_id="PY-CODE-018",
                    decision="block",
                    session_id="block-1",
                )
            ),
            stats_result_entry(
                StatsResultSpec(rule_id="PY-CODE-013", session_id="deny-1")
            ),
        ]
        return analyze([*noisy_context, *metrics, *enforced])

    def _assert_enrichment_stats(self, stats: ObjectDict) -> None:
        top_enforced = pair_counts(stats, "top_rules_enforced")
        enrichment = pair_counts(stats, "enrichment_rules")
        advisory = pair_counts(stats, "advisory_rules")
        assert top_enforced == {"PY-CODE-018": 1, "PY-CODE-013": 1}
        assert enrichment == {"ENRICHMENT": 4, "_ENRICHMENT_METRICS": 3}
        assert advisory.get("ENRICHMENT", 0) == 4
        assert "_ENRICHMENT_METRICS" not in top_enforced

    def test_enforcement_stats_ignore_enrichment_context_noise(self) -> None:
        stats = self._mixed_enrichment_stats()

        assert "top_rules_enforced" in stats
        self._assert_enrichment_stats(stats)
