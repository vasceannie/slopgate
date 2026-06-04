"""Human-readable and JSON hook activity reports."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from vibeforcer._types import object_dict, object_list

from ._analysis import analyze
from ._load import _default_log_path, load_entries

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
    print("VIBEFORCER HOOK ACTIVITY REPORT")
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
        short = str(path).replace(str(Path.home()), "~")
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


def _print_retry_patterns(stats: Mapping[str, object]) -> None:
    patterns = _pairs(stats, "retry_patterns")
    _print_pairs_section(
        title="Retry Patterns (same rule denied 2+ in one session)",
        pairs=patterns,
        formatter=lambda desc, count: f"  {count:3,}x  {desc}",
        empty_message="(none detected)",
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
) -> int:
    path = Path(log_path) if log_path else _default_log_path()
    if not path.exists():
        print(f"Log not found: {path}", file=sys.stderr)
        return 1

    label = f" (last {days} days)" if days else ""
    if not as_json:
        print(f"Loading {path}{label}...")

    entries = load_entries(path, days)
    stats = analyze(entries)

    if as_json:
        print(json.dumps(stats, indent=2, default=str))
    else:
        print_report(stats)

    return 0
