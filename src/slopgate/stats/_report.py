"""Human-readable and JSON hook activity reports."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from slopgate._types import object_dict, object_list

from ._analysis import analyze
from ._load import default_log_path, load_entries
from .improvement import ComparisonRequest, resolve_comparison

_PairList = list[tuple[str, int]]


def _as_pair_list(value: object) -> _PairList:
    pairs: _PairList = []
    for item in object_list(value):
        seq_item = object_list(item)
        if len(seq_item) == 2:
            label, count = seq_item
            if isinstance(label, str) and isinstance(count, int):
                pairs.append((label, count))
    return pairs


def _pairs(stats: Mapping[str, object], key: str) -> _PairList:
    """Safely extract a list of (str, int) pairs from the stats dict."""
    return _as_pair_list(stats.get(key, []))


def print_report(stats: Mapping[str, object]) -> None:
    print("=" * 70)
    print("SLOPGATE HOOK ACTIVITY REPORT")
    print("=" * 70)
    print(f"\nDate range: {stats['date_range']}")
    print(f"Total hook events: {stats['total_events']:,}")
    if stats.get("fixture_filtered"):
        print(f"Fixture/test sessions filtered: {stats['fixture_filtered']:,}")
    print(f"Unique sessions: {stats['sessions']}")

    raw_total = stats.get("total_events", 0)
    total = int(raw_total) if isinstance(raw_total, (int, float, str)) else 1
    print("\n--- Decisions ---")
    for decision, count in _pairs(stats, "by_decision"):
        pct = count / total * 100
        print(f"  {decision:12s} {count:6,}  ({pct:.1f}%)")

    print("\n--- Event Types ---")
    for event, count in _pairs(stats, "by_event"):
        print(f"  {event:25s} {count:6,}")

    _print_enforcement_rules(stats)
    _print_denied_rules(stats)
    _print_advisory_and_enrichment(stats)
    _print_denied_files(stats)
    _print_retry_patterns(stats)
    _print_churn_metrics(stats)
    _print_improvement_section(stats)
    _print_daily_volume(stats)
    _print_pairs_section(
        title="Severity Breakdown",
        pairs=_pairs(stats, "by_severity"),
        formatter=lambda sev, count: f"  {sev:10s} {count:6,}",
    )


def _print_enforcement_rules(stats: Mapping[str, object]) -> None:
    print("\n--- Top Enforcement Rules (deny/block) ---")
    for rule, count in _pairs(stats, "top_rules_enforced"):
        print(f"  {rule:25s} {count:5,}")


def _print_advisory_and_enrichment(stats: Mapping[str, object]) -> None:
    _print_pairs_section(
        title="Advisory Context Rules",
        pairs=_pairs(stats, "advisory_rules")[:10],
        formatter=lambda rule, count: f"  {rule:25s} {count:5,}",
        empty_message="(none detected)",
    )
    _print_pairs_section(
        title="Enrichment / Metrics Telemetry",
        pairs=_pairs(stats, "enrichment_rules")[:10],
        formatter=lambda rule, count: f"  {rule:25s} {count:5,}",
        empty_message="(none detected)",
    )


def _print_denied_rules(stats: Mapping[str, object]) -> None:
    print("\n--- Top Denied Rules ---")
    examples = stats.get("rule_examples", {})
    examples_dict = object_dict(examples)
    for rule, count in _pairs(stats, "top_rules_denied"):
        print(f"  {rule:25s} {count:5,}")
        if examples_dict:
            exs = object_list(examples_dict.get(rule))
            if exs:
                print(f"    └─ e.g. {str(exs[0])[:100]}")


def _print_denied_files(stats: Mapping[str, object]) -> None:
    print("\n--- Top Denied Files ---")
    for path, count in _pairs(stats, "top_files_denied"):
        short = path.replace(str(Path.home()), "~")
        print(f"  {count:4,}  {short}")


def _print_pairs_section(
    title: str,
    pairs: _PairList,
    formatter: Callable[[str, int], str],
    empty_message: str | None = None,
) -> None:
    print(f"\n--- {title} ---")
    if pairs:
        for label, count in pairs:
            print(formatter(label, count))
    elif empty_message is not None:
        print(f"  {empty_message}")
    print()


def _print_improvement_section(stats: Mapping[str, object]) -> None:
    improvement = object_dict(stats.get("improvement"))
    if not improvement:
        return
    print("\n--- Improvement (repo_strict headline) ---")
    legacy = object_dict(improvement.get("legacy_rows"))
    legacy_count = legacy.get("count", 0)
    if improvement.get("authoritative") is not True:
        print("  Authoritative: no (only legacy rows without fingerprints)")
    if isinstance(legacy_count, int) and legacy_count:
        print(f"  Legacy rows (diagnostic only): {legacy_count:,}")
    headline = object_dict(improvement.get("headline"))
    _print_rate_row(headline, "first_attempt_clean_rate", "First-attempt clean rate")
    _print_rate_row(headline, "repair_success_rate", "Observed repair success")
    blocking = object_dict(headline.get("blocking_per_100_mutations"))
    if blocking:
        print(
            "  Blocking per 100 mutations: "
            f"{_fmt(blocking.get('value'))} "
            f"({_fmt(blocking.get('numerator'))}/{_fmt(blocking.get('denominator'))})"
        )
    episodes = object_dict(improvement.get("episodes"))
    if episodes:
        print(
            "  Episodes: "
            f"resolved {_fmt(episodes.get('resolved'))}, "
            f"still-failing {_fmt(episodes.get('still_failing'))}, "
            f"no-followup {_fmt(episodes.get('no_observed_followup'))}, "
            f"provenance-changed {_fmt(episodes.get('provenance_changed'))}, "
            f"eval-error {_fmt(episodes.get('evaluation_error'))}"
        )
    comparison = object_dict(improvement.get("comparison"))
    if comparison:
        _print_comparison_summary(comparison)


def _print_rate_row(
    headline: Mapping[str, object], key: str, label: str
) -> None:
    payload = object_dict(headline.get(key))
    if not payload:
        return
    print(
        f"  {label}: {_fmt_pct(payload.get('rate'))} "
        f"({_fmt(payload.get('numerator'))}/{_fmt(payload.get('denominator'))})"
    )


def _print_retry_patterns(stats: Mapping[str, object]) -> None:
    patterns = _pairs(stats, "retry_patterns")
    _print_pairs_section(
        title="Retry Patterns (same rule denied 2+ in one session)",
        pairs=patterns,
        formatter=lambda desc, count: f"  {count:3,}x  {desc}",
        empty_message="(none detected)",
    )


def _fmt(value: object) -> str:
    return f"{value}" if value is not None else "n/a"


def _fmt_pct(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value) * 100:.1f}%"
    return "n/a"


def _print_comparison_summary(comparison: Mapping[str, object]) -> None:
    aggregate = object_dict(comparison.get("aggregate"))
    available = aggregate.get("available") is True
    print("  Comparison by " + _fmt(comparison.get("dimension")) + ":")
    if not available:
        reason = aggregate.get("suppression_reason")
        print(f"    aggregate unavailable: {_fmt(reason)}")
    for metric, delta in object_dict(comparison.get("metric_deltas")).items():
        entry = object_dict(delta)
        print(
            f"    {metric}: {_fmt(entry.get('baseline'))} -> "
            f"{_fmt(entry.get('candidate'))} "
            f"(delta {_fmt(entry.get('absolute'))})"
        )


def _print_daily_volume(stats: Mapping[str, object]) -> None:
    print("\n--- Daily Volume ---")
    for day, count in _pairs(stats, "daily_counts")[-14:]:
        bar = "\u2588" * min(count // 50, 60)
        print(f"  {day}  {count:5,}  {bar}")


def _print_churn_metrics(stats: Mapping[str, object]) -> None:
    print("\n--- Deny Churn ---")
    resolution_rate = stats.get("first_time_resolution_rate", 0.0)
    median_retries = stats.get("median_retries_before_resolution", 0.0)
    if isinstance(resolution_rate, (float, int)):
        print(f"  First-time resolution rate: {float(resolution_rate) * 100:.1f}%")
    print("  (legacy churn metric: counts single-denial scopes, not observed")
    print("   resolution; see the Improvement section for outcome-valid rates)")
    if isinstance(median_retries, (float, int)):
        print(f"  Median retries before resolution: {float(median_retries):.2f}")
    print("  Repeated deny rate by rule:")
    for rule, count in _pairs(stats, "repeated_deny_rate_by_rule")[:5]:
        print(f"    {rule:24s} {count:5,}")
    print("  Top looping files:")
    for path, count in _pairs(stats, "top_looping_files")[:5]:
        print(f"    {count:4,}  {path}")
    print("  Top pathless loop rules:")
    for rule, count in _pairs(stats, "top_pathless_loop_rules")[:5]:
        print(f"    {rule:24s} {count:5,}")


def run_stats(
    log_path: str | None = None,
    days: int | None = None,
    as_json: bool = False,
    comparison: ComparisonRequest | None = None,
) -> int:
    path = Path(log_path) if log_path else default_log_path()
    if not path.exists():
        print(f"Log not found: {path}", file=sys.stderr)
        return 1

    label = f" (last {days} days)" if days else ""
    if not as_json:
        print(f"Loading {path}{label}...")

    entries = load_entries(path, days)
    stats = analyze(entries)
    if comparison is not None:
        payload, error = resolve_comparison(entries, comparison)
        if error is not None:
            print(f"Comparison error: {error}", file=sys.stderr)
            return 1
        if payload is not None:
            improvement = object_dict(stats.get("improvement"))
            improvement["comparison"] = payload
            stats["improvement"] = improvement

    if as_json:
        print(json.dumps(stats, indent=2, default=str))
    else:
        print_report(stats)

    return 0
