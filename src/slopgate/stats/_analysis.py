"""Hook activity analysis helpers."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from slopgate._types import ObjectDict, object_dict, object_list, string_value
from slopgate.constants import METADATA_PATH, SESSION_ID

UNKNOWN_STATS_VALUE = "unknown"


@dataclass
class _Counters:
    """Mutable accumulators for the analysis pass."""

    by_event: Counter[str] = field(default_factory=Counter)
    by_decision: Counter[str] = field(default_factory=Counter)
    by_rule: Counter[str] = field(default_factory=Counter)
    enforcement_rules: Counter[str] = field(default_factory=Counter)
    advisory_rules: Counter[str] = field(default_factory=Counter)
    enrichment_rules: Counter[str] = field(default_factory=Counter)
    by_severity: Counter[str] = field(default_factory=Counter)
    by_tool: Counter[str] = field(default_factory=Counter)
    by_session: Counter[str] = field(default_factory=Counter)
    denies_by_file: Counter[str] = field(default_factory=Counter)
    denies_by_rule: Counter[str] = field(default_factory=Counter)
    rule_examples: dict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    daily_counts: Counter[str] = field(default_factory=Counter)
    session_deny_seq: dict[str, list[tuple[str, str, str]]] = field(
        default_factory=lambda: defaultdict(list),
    )
    deny_counts_by_key: Counter[tuple[str, str, str]] = field(default_factory=Counter)
    first_time_resolved: int = 0
    repeated_denies: int = 0
    retries_before_resolution: list[int] = field(default_factory=list)
    pathless_loop_rules: Counter[str] = field(default_factory=Counter)
    fixture_filtered: int = 0
    analyzed_events: int = 0


@dataclass(slots=True)
class _EntryContext:
    """Per-entry fields extracted once and reused across findings."""

    session: str
    tool: str
    ts_str: str


def _is_enrichment_rule(rule_id: str) -> bool:
    """Return True for internal enrichment/metrics telemetry rule rows."""
    return rule_id == "ENRICHMENT" or rule_id.startswith("_ENRICHMENT")


def _record_deny_metadata(meta: object, counters: _Counters) -> None:
    """Track file paths from a deny finding's metadata dict."""
    meta_dict = object_dict(meta)
    if not meta_dict:
        return
    path_val = string_value(meta_dict.get(METADATA_PATH))
    if path_val is not None:
        counters.denies_by_file[path_val] += 1
    for hit in object_list(meta_dict.get("hits")):
        if isinstance(hit, str):
            counters.denies_by_file[hit] += 1


def _process_finding(
    finding: ObjectDict,
    ectx: _EntryContext,
    counters: _Counters,
) -> bool:
    """Process a single finding dict. Returns True if it was a deny."""
    rule_id = str(finding.get("rule_id", UNKNOWN_STATS_VALUE))
    decision = finding.get("decision")
    severity = str(finding.get("severity", UNKNOWN_STATS_VALUE))

    counters.by_rule[rule_id] += 1
    if _is_enrichment_rule(rule_id):
        counters.enrichment_rules[rule_id] += 1
    if isinstance(decision, str):
        counters.by_decision[decision] += 1
        if decision in {"deny", "block"} and not _is_enrichment_rule(rule_id):
            counters.enforcement_rules[rule_id] += 1
        elif decision in {"ask", "warn", "context", "info"}:
            counters.advisory_rules[rule_id] += 1
    counters.by_severity[severity] += 1

    if decision not in {"deny", "block"}:
        return False

    counters.denies_by_rule[rule_id] += 1
    metadata = object_dict(finding.get("metadata", {}))
    path_val = string_value(metadata.get(METADATA_PATH)) or "__pathless__"
    counters.session_deny_seq[ectx.session].append((rule_id, ectx.tool, ectx.ts_str))
    counters.deny_counts_by_key[(ectx.session, rule_id, path_val)] += 1
    _record_deny_metadata(metadata, counters)
    if path_val == "__pathless__":
        counters.pathless_loop_rules[rule_id] += 1
    if len(counters.rule_examples[rule_id]) < 3:
        counters.rule_examples[rule_id].append(str(finding.get("message", "")))
    return True


def _classify_findings(
    findings: list[object], ectx: _EntryContext, counters: _Counters
) -> None:
    """Process all findings and record an entry-level allow when nothing fired."""
    has_deny = False
    has_any_decision = False
    for finding in findings:
        finding_dict = object_dict(finding)
        if not finding_dict:
            continue
        if _process_finding(finding_dict, ectx, counters):
            has_deny = True
        if finding_dict.get("decision") is not None:
            has_any_decision = True

    if not findings or (not has_deny and not has_any_decision):
        counters.by_decision["allow"] += 1


def _process_entry(entry: dict[str, object], counters: _Counters) -> None:
    """Process a single results.jsonl entry into the counters."""
    session = str(entry.get(SESSION_ID, UNKNOWN_STATS_VALUE))
    if session.startswith("fixture-") or session.startswith("test-"):
        counters.fixture_filtered += 1
        return

    counters.analyzed_events += 1
    event = str(entry.get("event_name", UNKNOWN_STATS_VALUE))
    counters.by_event[event] += 1
    tool = str(entry.get("tool_name", "")) or "(none)"
    counters.by_tool[tool] += 1
    counters.by_session[session] += 1

    ts_str = str(entry.get("timestamp", ""))
    if ts_str:
        counters.daily_counts[ts_str[:10]] += 1

    findings = object_list(entry.get("findings"))
    ectx = _EntryContext(session=session, tool=tool, ts_str=ts_str)
    _classify_findings(findings, ectx, counters)


def _compute_retry_patterns(counters: _Counters) -> Counter[str]:
    retry_counts: Counter[str] = Counter()
    for session, denies in counters.session_deny_seq.items():
        rc: Counter[str] = Counter(r for r, _, _ in denies)
        for rule_id, count in rc.items():
            if count >= 2:
                retry_counts[f"{rule_id} (session {session[:8]}...)"] = count
    return retry_counts


def _record_repeated_deny_metrics(
    counters: _Counters,
) -> tuple[Counter[str], Counter[str]]:
    top_looping_files: Counter[str] = Counter()
    repeated_by_rule: Counter[str] = Counter()
    for (_, rule_id, path), count in counters.deny_counts_by_key.items():
        if count <= 1:
            counters.first_time_resolved += 1
            continue
        counters.repeated_denies += 1
        counters.retries_before_resolution.append(count - 1)
        repeated_by_rule[rule_id] += 1
        top_looping_files[path] += count
    return repeated_by_rule, top_looping_files


def _median(values: list[int]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    mid = len(sorted_vals) // 2
    if len(sorted_vals) % 2 == 1:
        return float(sorted_vals[mid])
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0


def _first_time_resolution_rate(counters: _Counters) -> float:
    total_resolution = counters.first_time_resolved + counters.repeated_denies
    return counters.first_time_resolved / total_resolution if total_resolution else 0.0


def _date_range(counters: _Counters) -> str:
    dates = sorted(counters.daily_counts.keys())
    return f"{dates[0]} to {dates[-1]}" if dates else UNKNOWN_STATS_VALUE


def analyze(entries: list[dict[str, object]]) -> ObjectDict:
    counters = _Counters()
    for entry in entries:
        _process_entry(entry, counters)

    retry_counts = _compute_retry_patterns(counters)
    repeated_by_rule, top_looping_files = _record_repeated_deny_metrics(counters)

    return {
        "raw_total_events": len(entries),
        "analyzed_events": counters.analyzed_events,
        "total_events": counters.analyzed_events,
        "fixture_filtered": counters.fixture_filtered,
        "date_range": _date_range(counters),
        "by_event": counters.by_event.most_common(),
        "by_decision": counters.by_decision.most_common(),
        "by_severity": counters.by_severity.most_common(),
        "top_rules_denied": counters.denies_by_rule.most_common(20),
        "top_rules_enforced": counters.enforcement_rules.most_common(20),
        "advisory_rules": counters.advisory_rules.most_common(20),
        "enrichment_rules": counters.enrichment_rules.most_common(20),
        "top_files_denied": counters.denies_by_file.most_common(15),
        "top_tools": counters.by_tool.most_common(10),
        "sessions": len(counters.by_session),
        "daily_counts": sorted(counters.daily_counts.items()),
        "retry_patterns": retry_counts.most_common(15),
        "rule_examples": dict(counters.rule_examples),
        "first_time_resolution_rate": round(_first_time_resolution_rate(counters), 4),
        "repeated_deny_rate_by_rule": repeated_by_rule.most_common(20),
        "median_retries_before_resolution": _median(counters.retries_before_resolution),
        "top_looping_files": top_looping_files.most_common(15),
        "top_pathless_loop_rules": counters.pathless_loop_rules.most_common(15),
    }
