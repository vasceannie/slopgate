"""Deprecated denial-churn metrics with honest names."""

from __future__ import annotations

from collections import Counter
from statistics import median

from slopgate._types import ObjectDict
from slopgate.constants import STATS_TOP_RULE_LIMIT

from .records import NormalizedEvent, TargetType


def _denial_counts(
    events: tuple[NormalizedEvent, ...],
) -> tuple[Counter[tuple[str, str, str]], Counter[str]]:
    deny_counts: Counter[tuple[str, str, str]] = Counter()
    pathless_rules: Counter[str] = Counter()
    for event in events:
        for finding in event.distinct_findings():
            if not finding.is_blocking:
                continue
            target = finding.targets[0]
            target_key = f"{target.target_type.value}:{target.value}"
            deny_counts[(event.session_id, finding.rule_id, target_key)] += 1
            if target.target_type is not TargetType.FILE:
                pathless_rules[finding.rule_id] += 1
    return deny_counts, pathless_rules


def legacy_churn(events: tuple[NormalizedEvent, ...]) -> ObjectDict:
    """Measure repeated denial keys without claiming observed recovery."""
    deny_counts, pathless_rules = _denial_counts(events)
    repeated_by_rule: Counter[str] = Counter()
    looping_targets: Counter[str] = Counter()
    session_rule_frequency: Counter[str] = Counter()
    target_labels: dict[str, str] = {}
    session_labels: dict[str, str] = {}
    extra_denials: list[int] = []
    single_occurrence = 0
    for (session_id, rule_id, target_key), count in deny_counts.items():
        if count == 1:
            single_occurrence += 1
            continue
        repeated_by_rule[rule_id] += 1
        target_type = target_key.partition(":")[0]
        target_label = target_labels.setdefault(
            target_key, f"{target_type}:target-{len(target_labels) + 1}"
        )
        session_label = session_labels.setdefault(
            session_id, f"session-{len(session_labels) + 1}"
        )
        looping_targets[target_label] += count
        extra_denials.append(count - 1)
        session_rule_frequency[f"{rule_id} ({session_label})"] += count
    total_keys = len(deny_counts)
    ratio = round(single_occurrence / total_keys, 4) if total_keys else None
    return {
        "single_occurrence_deny_key_ratio": ratio,
        "median_extra_denials_per_repeated_key": (
            median(extra_denials) if extra_denials else None
        ),
        "repeated_deny_key_count_by_rule": repeated_by_rule.most_common(
            STATS_TOP_RULE_LIMIT
        ),
        "session_rule_denial_frequency": session_rule_frequency.most_common(15),
        "top_looping_files": looping_targets.most_common(15),
        "top_pathless_loop_rules": pathless_rules.most_common(15),
    }
