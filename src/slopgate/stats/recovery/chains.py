"""Deterministic recovery chains over normalized trace-schema-v2 events."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final

from slopgate._types import ObjectDict
from slopgate.constants import MAX_RECOVERY_CHAINS_PER_EVENT, POST_TOOL_USE, STOP

from .records import NormalizedEvent, RecoveryTarget, TargetType, ToolOutcome

_TERMINAL_EVENTS: Final = frozenset(
    {STOP, "SubagentStop", "SessionEnd", "TaskCompleted"}
)


class ChainStatus(str, Enum):
    RECOVERED = "recovered"
    ABANDONED = "abandoned"
    OPEN = "open_censored"


@dataclass(frozen=True, slots=True)
class _ChainKey:
    session_id: str
    repo_root: str | None
    enforcement_mode: str
    rule_id: str
    rule_variant: str | None
    target: RecoveryTarget


@dataclass(slots=True)
class ChainState:
    """Mutable accumulator for one ordered recovery attempt."""

    key: _ChainKey
    initial: NormalizedEvent
    retries: list[NormalizedEvent] = field(default_factory=list)
    status: ChainStatus = ChainStatus.OPEN
    first_rule_cleared: bool | None = None
    first_operation_succeeded: bool | None = None
    first_fingerprint_unchanged: bool | None = None
    compound_first_retry_blocked: bool = False


def recovery_rate(numerator: int, denominator: int) -> ObjectDict:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "percentage": (
            round(numerator / denominator * 100, 1) if denominator else None
        ),
    }


def _recovery_targets(event: NormalizedEvent) -> frozenset[RecoveryTarget]:
    targets = {target for finding in event.findings for target in finding.targets}
    targets.update(
        RecoveryTarget(TargetType.FILE, path) for path in event.candidate_paths
    )
    return frozenset(targets)


def _matches(event: NormalizedEvent, state: ChainState) -> bool:
    key = state.key
    return (
        event.session_id == key.session_id
        and event.resolved_repo_root == key.repo_root
        and event.enforcement_mode == key.enforcement_mode
        and key.target in _recovery_targets(event)
    )


def _operation_succeeded(
    event: NormalizedEvent, *, has_blocking_findings: bool
) -> bool | None:
    if event.event_name != POST_TOOL_USE:
        return None
    return event.tool_outcome is ToolOutcome.SUCCESS and not has_blocking_findings


def _observe_retry(event: NormalizedEvent, state: ChainState) -> None:
    state.retries.append(event)
    has_blocking_findings = any(finding.is_blocking for finding in event.findings)
    rule_cleared = not any(
        finding.rule_id == state.key.rule_id
        and finding.rule_variant == state.key.rule_variant
        and finding.is_blocking
        for finding in event.findings
    )
    operation_succeeded = _operation_succeeded(
        event,
        has_blocking_findings=has_blocking_findings,
    )
    if len(state.retries) == 1:
        state.first_rule_cleared = rule_cleared
        state.first_operation_succeeded = operation_succeeded
        state.compound_first_retry_blocked = rule_cleared and has_blocking_findings
        initial_fingerprint = state.initial.attempt_fingerprint
        retry_fingerprint = event.attempt_fingerprint
        if initial_fingerprint is not None and retry_fingerprint is not None:
            state.first_fingerprint_unchanged = initial_fingerprint == retry_fingerprint
    if operation_succeeded and rule_cleared:
        state.status = ChainStatus.RECOVERED


def _start_chains(
    event: NormalizedEvent,
    active: dict[_ChainKey, ChainState],
    chains: list[ChainState],
) -> None:
    created = 0
    for finding in event.findings:
        if not finding.is_blocking:
            continue
        for target in finding.targets:
            if created >= MAX_RECOVERY_CHAINS_PER_EVENT:
                return
            key = _ChainKey(
                session_id=event.session_id,
                repo_root=event.resolved_repo_root,
                enforcement_mode=event.enforcement_mode,
                rule_id=finding.rule_id,
                rule_variant=finding.rule_variant,
                target=target,
            )
            if key in active:
                continue
            state = ChainState(key=key, initial=event)
            active[key] = state
            chains.append(state)
            created += 1


def _close_session(event: NormalizedEvent, active: dict[_ChainKey, ChainState]) -> None:
    for key, state in tuple(active.items()):
        if key.session_id == event.session_id:
            state.status = ChainStatus.ABANDONED
            del active[key]


def _advance_chains(
    event: NormalizedEvent, active: dict[_ChainKey, ChainState]
) -> None:
    for key, state in tuple(active.items()):
        if not _matches(event, state):
            continue
        _observe_retry(event, state)
        if state.status is ChainStatus.RECOVERED:
            del active[key]


def _recovery_rates(chains: list[ChainState]) -> ObjectDict:
    first_retries = [state for state in chains if state.first_rule_cleared is not None]
    operation_observations = [
        state for state in chains if state.first_operation_succeeded is not None
    ]
    fingerprint_observations = [
        state for state in chains if state.first_fingerprint_unchanged is not None
    ]
    return {
        "first_retry_rule_clearance": recovery_rate(
            sum(state.first_rule_cleared is True for state in first_retries),
            len(first_retries),
        ),
        "first_retry_operation_success": recovery_rate(
            sum(
                state.first_operation_succeeded is True
                for state in operation_observations
            ),
            len(operation_observations),
        ),
        "unchanged_first_retry": recovery_rate(
            sum(
                state.first_fingerprint_unchanged is True
                for state in fingerprint_observations
            ),
            len(fingerprint_observations),
        ),
        "changed_first_retry": recovery_rate(
            sum(
                state.first_fingerprint_unchanged is False
                for state in fingerprint_observations
            ),
            len(fingerprint_observations),
        ),
    }


def summarize_chains(chains: list[ChainState]) -> ObjectDict:
    statuses = {status: 0 for status in ChainStatus}
    for state in chains:
        statuses[state.status] += 1
    return {
        "summary": {
            "chains": len(chains),
            "recovered": statuses[ChainStatus.RECOVERED],
            "abandoned": statuses[ChainStatus.ABANDONED],
            "open_censored": statuses[ChainStatus.OPEN],
        },
        "rates": _recovery_rates(chains),
    }


def build_chains(events: tuple[NormalizedEvent, ...]) -> list[ChainState]:
    active: dict[_ChainKey, ChainState] = {}
    chains: list[ChainState] = []
    for event in sorted(events, key=lambda item: item.source_index):
        if event.is_legacy:
            continue
        if event.event_name in _TERMINAL_EVENTS:
            _close_session(event, active)
            continue
        _advance_chains(event, active)
        _start_chains(event, active, chains)
    return chains
