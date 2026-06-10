"""Unit tests for stats.analyze() and related functions."""

from __future__ import annotations

from datetime import datetime, timezone

from slopgate._types import ObjectDict, object_dict, object_list
from slopgate.stats import analyze, parse_timestamp


def _analyze(entries: list[ObjectDict]) -> ObjectDict:
    return object_dict(analyze(entries))


def _pair_counts(stats: ObjectDict, key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in object_list(stats.get(key)):
        pair = object_list(item)
        if len(pair) == 2:
            name, count = pair
            if isinstance(name, str) and isinstance(count, int):
                counts[name] = count
    return counts


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
    def _entry(
        self,
        event: str = "PreToolUse",
        rule_id: str = "GIT-001",
        decision: str = "deny",
        session: str = "s1",
    ) -> ObjectDict:
        return {
            "timestamp": "2026-04-01T12:00:00+00:00",
            "event_name": event,
            "session_id": session,
            "tool_name": "Bash",
            "findings": [
                {
                    "rule_id": rule_id,
                    "decision": decision,
                    "severity": "HIGH",
                    "message": f"{rule_id} triggered",
                    "metadata": {"path": "src/main.py"},
                },
            ],
        }

    def test_counts_deny_decision(self) -> None:
        stats = _analyze([self._entry()])
        decisions = _pair_counts(stats, "by_decision")
        assert decisions.get("deny") == 1, "deny count must be 1"

    def test_context_only_not_counted_as_allow(self) -> None:
        entry = self._entry(decision="context")
        stats = _analyze([entry])
        decisions = _pair_counts(stats, "by_decision")
        assert decisions.get("context", 0) == 1, (
            "context-only findings must be counted as context"
        )
        assert decisions.get("allow", 0) == 0, (
            "context-only must not inflate allow count"
        )

    def test_no_findings_counted_as_allow(self) -> None:
        entry: ObjectDict = {
            "timestamp": "2026-04-01T12:00:00+00:00",
            "event_name": "PreToolUse",
            "session_id": "s1",
            "tool_name": "Read",
            "findings": [],
        }
        stats = _analyze([entry])
        decisions = _pair_counts(stats, "by_decision")
        assert decisions.get("allow") == 1, "empty findings must count as allow"

    def test_fixture_sessions_filtered(self) -> None:
        entry = self._entry(session="fixture-abc")
        stats = _analyze([entry])
        assert stats["fixture_filtered"] == 1, "fixture sessions must be filtered"

    def test_self_test_filtering_exposes_raw_and_analyzed_event_counts(self) -> None:
        fixture_entry = self._entry(session="fixture-abc")
        real_entry = self._entry(session="real-session")

        stats = _analyze([fixture_entry, real_entry])

        assert stats["raw_total_events"] == 2
        assert stats["analyzed_events"] == 1
        assert stats["total_events"] == 1
        decisions = _pair_counts(stats, "by_decision")
        assert decisions.get("deny") == 1

    def test_retry_patterns_detected(self) -> None:
        entries = [self._entry(session="s1")] * 3
        stats = _analyze(entries)
        retries = object_list(stats.get("retry_patterns"))
        assert retries == [("GIT-001 (session s1...)", 3)]

    def _blocking_churn_metrics(self, stats: ObjectDict) -> dict[str, int | None]:
        expected_counts = {
            "top_rules_enforced": ("QUALITY-LINT-001", 2),
            "top_rules_denied": ("QUALITY-LINT-001", 2),
            "top_files_denied": ("src/main.py", 2),
            "retry_patterns": ("QUALITY-LINT-001 (session s1...)", 2),
            "repeated_deny_rate_by_rule": ("QUALITY-LINT-001", 1),
            "top_looping_files": ("src/main.py", 2),
        }
        return {
            key: _pair_counts(stats, key).get(expected_key)
            for key, (expected_key, _expected_count) in expected_counts.items()
        }

    def test_blocking_findings_count_for_denied_file_churn_metrics(self) -> None:
        entries = [
            self._entry(rule_id="QUALITY-LINT-001", decision="block", session="s1"),
            self._entry(rule_id="QUALITY-LINT-001", decision="block", session="s1"),
        ]
        expected = {
            "top_rules_enforced": 2,
            "top_rules_denied": 2,
            "top_files_denied": 2,
            "retry_patterns": 2,
            "repeated_deny_rate_by_rule": 1,
            "top_looping_files": 2,
        }

        assert self._blocking_churn_metrics(_analyze(entries)) == expected

    def test_daily_counts(self) -> None:
        stats = _analyze([self._entry()])
        daily = _pair_counts(stats, "daily_counts")
        assert "2026-04-01" in daily, "daily count must include the entry date"

    def test_rule_examples_capped_at_three(self) -> None:
        entries = [self._entry()] * 5
        stats = _analyze(entries)
        examples = object_dict(stats.get("rule_examples"))
        assert len(string_list(examples, "GIT-001")) <= 3, (
            "rule examples must be capped at 3"
        )

    def test_churn_metrics_include_repeated_deny_rates(self) -> None:
        entries = [
            self._entry(rule_id="PY-CODE-009", session="s1"),
            self._entry(rule_id="PY-CODE-009", session="s1"),
            self._entry(rule_id="PY-CODE-010", session="s2"),
        ]
        stats = _analyze(entries)
        repeated = _pair_counts(stats, "repeated_deny_rate_by_rule")
        assert repeated.get("PY-CODE-009") == 1
        resolution_rate = stats.get("first_time_resolution_rate", 0.0)
        assert isinstance(resolution_rate, (float, int))
        assert float(resolution_rate) < 1.0

    def test_pathless_rules_are_tracked(self) -> None:
        entry = self._entry(rule_id="SHELL-001")
        entry["findings"] = [
            {
                "rule_id": "SHELL-001",
                "decision": "deny",
                "severity": "HIGH",
                "message": "No shell",
                "metadata": {},
            }
        ]
        stats = _analyze([entry, entry])
        pathless = _pair_counts(stats, "top_pathless_loop_rules")
        assert pathless.get("SHELL-001", 0) >= 1

    def _mixed_enrichment_stats(self) -> ObjectDict:
        noisy_context = [
            self._entry(rule_id="ENRICHMENT", decision="context", session=f"ctx-{idx}")
            for idx in range(4)
        ]
        metrics = [
            self._entry(
                rule_id="_ENRICHMENT_METRICS", decision="info", session=f"met-{idx}"
            )
            for idx in range(3)
        ]
        enforced = [
            self._entry(rule_id="PY-CODE-018", decision="block", session="block-1"),
            self._entry(rule_id="PY-CODE-013", decision="deny", session="deny-1"),
        ]
        return _analyze([*noisy_context, *metrics, *enforced])

    def _assert_enrichment_stats(self, stats: ObjectDict) -> None:
        top_enforced = _pair_counts(stats, "top_rules_enforced")
        enrichment = _pair_counts(stats, "enrichment_rules")
        advisory = _pair_counts(stats, "advisory_rules")
        assert top_enforced == {"PY-CODE-018": 1, "PY-CODE-013": 1}
        assert enrichment == {"ENRICHMENT": 4, "_ENRICHMENT_METRICS": 3}
        assert advisory.get("ENRICHMENT", 0) == 4
        assert "_ENRICHMENT_METRICS" not in top_enforced

    def test_enforcement_stats_ignore_enrichment_context_noise(self) -> None:
        stats = self._mixed_enrichment_stats()

        assert "top_rules_enforced" in stats
        self._assert_enrichment_stats(stats)
