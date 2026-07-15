"""Human-readable and JSON hook activity reports."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from slopgate._types import object_dict, object_list
from slopgate.constants import UNKNOWN_VALUE

from ._analysis import analyze
from ._load import default_log_path, load_entries
from .recovery.scopes import RecoveryScope

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

    _print_distribution(stats, "Event Outcomes", "event_outcomes")
    _print_distribution(stats, "Finding Decisions", "finding_decisions")

    print("\n--- Event Types ---")
    for event, count in _pairs(stats, "by_event"):
        print(f"  {event:25s} {count:6,}")

    _print_enforcement_rules(stats)
    _print_denied_rules(stats)
    _print_advisory_and_enrichment(stats)
    _print_denied_files(stats)
    _print_recovery(stats)
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


def _print_distribution(
    stats: Mapping[str, object],
    title: str,
    key: str,
) -> None:
    section = object_dict(stats.get(key))
    raw_total = section.get("total")
    total = raw_total if isinstance(raw_total, int) else 0
    print(f"\n--- {title} ---")
    counts = _as_pair_list(section.get("counts"))
    if not counts:
        print("  (none detected)")
        return
    for label, count in counts:
        print(f"  {label:24s} {count:6,}  {_format_fraction(count, total)}")


def _format_fraction(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "—"
    percentage = numerator / denominator * 100
    return f"{percentage:.1f}% ({numerator}/{denominator})"


def _rate_text(value: object) -> str:
    rate = object_dict(value)
    numerator = rate.get("numerator")
    denominator = rate.get("denominator")
    if not isinstance(numerator, int) or not isinstance(denominator, int):
        return "—"
    return _format_fraction(numerator, denominator)


def _print_recovery_section(recovery: Mapping[str, object], title: str) -> None:
    summary, rates = map(
        object_dict,
        (recovery.get("summary"), recovery.get("rates")),
    )
    print(f"\n--- {title} ---")
    print(
        "  Chains: "
        f"{summary.get('chains', 0)}  "
        f"recovered={summary.get('recovered', 0)}  "
        f"abandoned={summary.get('abandoned', 0)}  "
        f"open/censored={summary.get('open_censored', 0)}"
    )
    print(
        "  1st retry rule clearance: "
        f"{_rate_text(rates.get('first_retry_rule_clearance'))}"
    )
    print(
        "  1st retry operation success: "
        f"{_rate_text(rates.get('first_retry_operation_success'))}"
    )
    rules = [object_dict(item) for item in object_list(recovery.get("rules"))]
    if not rules:
        print("  Rule evidence: —")
        return
    print("  Rule evidence:")
    for rule in rules[:10]:
        raw_chains = rule.get("chains")
        chain_count = raw_chains if isinstance(raw_chains, int) else 0
        print(
            f"    {str(rule.get('label', UNKNOWN_VALUE)):32s} "
            f"chains={chain_count:>4}  "
            f"success={_rate_text(rule.get('first_retry_operation_success')):>13s}  "
            f"unchanged={_rate_text(rule.get('unchanged_first_retry')):>13s}  "
            f"eventual={_rate_text(rule.get('eventual_recovery')):>13s}  "
            f"class={rule.get('primary_classification', 'unclassified')}"
        )


def _print_recovery(stats: Mapping[str, object]) -> None:
    recovery = object_dict(stats.get("recovery"))
    scope_reports = object_dict(recovery.get("scope_reports"))
    if scope_reports:
        for scope_name, report in scope_reports.items():
            _print_recovery_section(
                object_dict(report),
                f"Recovery Chains: {scope_name}",
            )
        return
    scope = str(recovery.get("scope", RecoveryScope.MANAGED.value))
    _print_recovery_section(recovery, f"Recovery Chains: {scope}")


def _print_daily_volume(stats: Mapping[str, object]) -> None:
    print("\n--- Daily Volume ---")
    for day, count in _pairs(stats, "daily_counts")[-14:]:
        bar = "\u2588" * min(count // 50, 60)
        print(f"  {day}  {count:5,}  {bar}")


def _print_churn_metrics(stats: Mapping[str, object]) -> None:
    legacy_metrics = object_dict(stats.get("legacy_metrics"))
    churn = object_dict(legacy_metrics.get("legacy_churn"))
    print("\n--- Legacy Denial Churn (deprecated) ---")
    single_ratio = churn.get("single_occurrence_deny_key_ratio")
    median_extra = churn.get("median_extra_denials_per_repeated_key")
    formatted_values: list[str] = []
    for value, multiplier, precision in ((single_ratio, 100, 1), (median_extra, 1, 2)):
        formatted = "—"
        if isinstance(value, (float, int)):
            formatted = f"{float(value) * multiplier:.{precision}f}"
        formatted_values.append(formatted)
    ratio_text, median_text = formatted_values
    ratio_suffix = "%" if ratio_text != "—" else ""
    print(f"  Single-occurrence deny-key ratio: {ratio_text}{ratio_suffix}")
    print(f"  Median extra denials per repeated key: {median_text}")
    _print_pairs_section(
        title="Repeated Deny-Key Count by Rule",
        pairs=_pairs(churn, "repeated_deny_key_count_by_rule")[:5],
        formatter=lambda rule, count: f"  {rule:24s} {count:5,}",
        empty_message="(none detected)",
    )
    _print_pairs_section(
        title="Session / Rule Denial Frequency",
        pairs=_pairs(churn, "session_rule_denial_frequency")[:5],
        formatter=lambda description, count: f"  {count:4,}  {description}",
        empty_message="(none detected)",
    )
    _print_pairs_section(
        title="Top Looping Files",
        pairs=_pairs(churn, "top_looping_files")[:5],
        formatter=lambda path, count: f"  {count:4,}  {path}",
        empty_message="(none detected)",
    )
    _print_pairs_section(
        title="Top Pathless Loop Rules",
        pairs=_pairs(churn, "top_pathless_loop_rules")[:5],
        formatter=lambda rule, count: f"  {rule:24s} {count:5,}",
        empty_message="(none detected)",
    )


def run_stats(
    log_path: str | None = None,
    days: int | None = None,
    as_json: bool = False,
    scope: RecoveryScope = RecoveryScope.MANAGED,
) -> int:
    path = Path(log_path) if log_path else default_log_path()
    if not path.exists():
        print(f"Log not found: {path}", file=sys.stderr)
        return 1

    label = f" (last {days} days)" if days else ""
    if not as_json:
        print(f"Loading {path}{label}...")

    entries = load_entries(path, days)
    stats = analyze(entries, scope=scope)

    if as_json:
        print(json.dumps(stats, indent=2, default=str))
    else:
        print_report(stats)

    return 0
