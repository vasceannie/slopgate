"""Redacted representative evidence selected from recovery chains."""

from __future__ import annotations

from collections import OrderedDict

from slopgate._types import ObjectDict

from .chains import ChainState, ChainStatus


def _archetypes(chain: ChainState) -> tuple[str, ...]:
    names: list[str] = []
    if chain.first_fingerprint_unchanged is True:
        names.append("unchanged_retry_loop")
    if (
        chain.first_fingerprint_unchanged is False
        and chain.status is not ChainStatus.RECOVERED
    ):
        names.append("changed_retry_failure")
    interventions = set(chain.initial.intervention_tags)
    for retry in chain.retries:
        interventions.update(retry.intervention_tags)
    if interventions and chain.status is ChainStatus.RECOVERED:
        names.append("recovery_after_intervention")
    if chain.compound_first_retry_blocked:
        names.append("compound_rule_friction")
    if chain.status is ChainStatus.ABANDONED:
        names.append("explicit_abandonment")
    return tuple(names)


def _sequence(chain: ChainState, archetype: str) -> ObjectDict:
    events = (chain.initial, *chain.retries)
    steps: list[ObjectDict] = []
    for index, event in enumerate(events):
        step: ObjectDict = {
            "evaluation_id": event.evaluation_id,
            "timestamp": event.timestamp,
            "event_name": event.event_name,
            "event_outcome": event.event_outcome.value,
            "tool_outcome": event.tool_outcome.value,
            "attempt_fingerprint": event.attempt_fingerprint,
            "intervention_tags": list(event.intervention_tags),
        }
        if index:
            step["original_rule_cleared"] = not any(
                finding.rule_id == chain.key.rule_id
                and finding.rule_variant == chain.key.rule_variant
                and finding.is_blocking
                for finding in event.findings
            )
        steps.append(step)
    label = (
        chain.key.rule_id
        if chain.key.rule_variant is None
        else f"{chain.key.rule_id} / {chain.key.rule_variant}"
    )
    return {
        "archetype": archetype,
        "evidence_id": chain.initial.evaluation_id
        or f"source-{chain.initial.source_index}",
        "rule": label,
        "repository": "redacted" if chain.key.repo_root is not None else None,
        "enforcement_mode": chain.key.enforcement_mode,
        "target_type": chain.key.target.target_type.value,
        "target": "redacted",
        "correlation_confidence": chain.initial.correlation_confidence.value,
        "platform_capability": chain.initial.platform_capability,
        "events": steps,
    }


def representative_sequences(chains: list[ChainState]) -> list[ObjectDict]:
    """Return the first stable, redacted sequence for each observed archetype."""
    selected: OrderedDict[str, ChainState] = OrderedDict()
    for chain in chains:
        for archetype in _archetypes(chain):
            selected.setdefault(archetype, chain)
    return [_sequence(chain, archetype) for archetype, chain in selected.items()]
