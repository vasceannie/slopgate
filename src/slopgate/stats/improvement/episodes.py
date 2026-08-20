"""Episode evaluation over parsed result records.

Anchors one rule-local repair episode per first block and advances it with
comparable follow-ups. Comparable means the same structural scope identity
(session, repo, semantic family, normalized target paths) and the same
provenance (enforcement mode, version, policy and guidance fingerprints).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .parsing import parse_result_record
from .scope_model import (
    STATE_EVALUATION_ERROR,
    STATE_NO_FOLLOWUP,
    STATE_PROVENANCE_CHANGED,
    STATE_RESOLVED,
    STATE_STILL_FAILING,
    EpisodeEvaluation,
    ResultRecord,
    RepairEpisode,
    StructuralKey,
    timestamp_key,
)

_RuleBuckets = dict[str, RepairEpisode]


@dataclass(slots=True)
class _FollowupCounters:
    """Mutable rule-level persistence tallies shared across episodes."""

    followups: dict[str, int]
    enforcing: dict[str, int]

    def count_followup(self, rule_id: str) -> None:
        self.followups[rule_id] = self.followups.get(rule_id, 0) + 1

    def count_enforcing(self, rule_id: str) -> None:
        self.enforcing[rule_id] = self.enforcing.get(rule_id, 0) + 1


def parse_result_records(entries: Sequence[object]) -> list[ResultRecord]:
    """Parse and order records from ``results.jsonl`` entry dicts."""
    records: list[ResultRecord] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        typed_entry: dict[str, object] = {
            str(key): value for key, value in entry.items()
        }
        record = parse_result_record(typed_entry, index)
        if record is not None:
            records.append(record)
    records.sort(key=lambda record: (timestamp_key(record.timestamp), record.index))
    return records


def evaluate_first_observed(records: Sequence[ResultRecord]) -> list[ResultRecord]:
    """Return the first observed mutating record per cohort scope."""
    seen: set[tuple[StructuralKey, tuple[str, str, str, str]]] = set()
    first_observed: list[ResultRecord] = []
    for record in records:
        if not record.mutating:
            continue
        key = record.cohort_key
        if key in seen:
            continue
        seen.add(key)
        first_observed.append(record)
    return first_observed


def evaluate_episodes(records: Sequence[ResultRecord]) -> EpisodeEvaluation:
    """Anchor rule-local repair episodes and scan comparable follow-ups."""
    open_by_structural: dict[StructuralKey, _RuleBuckets] = {}
    closed: list[RepairEpisode] = []
    counters = _FollowupCounters(followups={}, enforcing={})

    for record in records:
        _process_record(open_by_structural, record, closed, counters)

    for bucket in open_by_structural.values():
        for episode in bucket.values():
            closed.append(_terminal_state(episode))

    closed.sort(key=lambda episode: episode.anchor.index)
    return EpisodeEvaluation(
        records=list(records),
        episodes=closed,
        rule_followups=counters.followups,
        rule_enforcing_followups=counters.enforcing,
        first_observed=evaluate_first_observed(records),
    )


def _process_record(
    open_by_structural: dict[StructuralKey, _RuleBuckets],
    record: ResultRecord,
    closed: list[RepairEpisode],
    counters: _FollowupCounters,
) -> None:
    if not record.blocking_rules:
        bucket = open_by_structural.get(record.structural_key)
        if bucket is not None:
            _advance_open_episodes(bucket, record, closed, counters)
        return
    rule_keys = {
        rule_id: record.structural_key_for_rule(rule_id)
        for rule_id in record.blocking_rules
    }
    for key in set(rule_keys.values()):
        bucket = open_by_structural.get(key)
        if bucket is not None:
            _advance_open_episodes(bucket, record, closed, counters)
        if bucket is None:
            bucket = {}
            open_by_structural[key] = bucket
        for rule_id, rule_key in rule_keys.items():
            if rule_key == key and rule_id not in bucket:
                bucket[rule_id] = RepairEpisode(rule_id=rule_id, anchor=record)


def _advance_open_episodes(
    bucket: _RuleBuckets,
    record: ResultRecord,
    closed: list[RepairEpisode],
    counters: _FollowupCounters,
) -> None:
    """Apply one record as follow-up evidence to every open episode."""
    for rule_id in list(bucket):
        episode = bucket[rule_id]
        if record.provenance_key != episode.anchor.provenance_key:
            episode.provenance_divergence = True
            episode.state = STATE_PROVENANCE_CHANGED
            closed.append(episode)
            del bucket[rule_id]
            continue
        counters.count_followup(rule_id)
        episode.followups += 1
        if _classify_followup(episode, record, rule_id, counters):
            closed.append(episode)
            del bucket[rule_id]


def _classify_followup(
    episode: RepairEpisode,
    record: ResultRecord,
    rule_id: str,
    counters: _FollowupCounters,
) -> bool:
    """Record follow-up evidence; return True when the episode resolves."""
    if rule_id in record.blocking_rules:
        episode.last_enforcing = True
        episode.last_error = False
        counters.count_enforcing(rule_id)
        return False
    if rule_id in record.errored_rules:
        episode.last_error = True
        episode.last_enforcing = False
        return False
    episode.state = STATE_RESOLVED
    episode.resolved_record = record
    return True


def _terminal_state(episode: RepairEpisode) -> RepairEpisode:
    """Close an unresolved episode with its observable terminal state."""
    if episode.state == STATE_PROVENANCE_CHANGED:
        return episode
    if episode.followups > 0:
        if episode.last_enforcing:
            episode.state = STATE_STILL_FAILING
        elif episode.last_error:
            episode.state = STATE_EVALUATION_ERROR
        else:
            episode.state = STATE_STILL_FAILING
        return episode
    if episode.provenance_divergence:
        episode.state = STATE_PROVENANCE_CHANGED
        return episode
    episode.state = STATE_NO_FOLLOWUP
    return episode
