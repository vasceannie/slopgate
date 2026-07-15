"""Ordered recovery-chain behavior through the public stats analyzer."""

from __future__ import annotations

from dataclasses import dataclass

from slopgate._types import ObjectDict, object_dict, object_list
from slopgate.constants import METADATA_DECISION
from slopgate.stats import analyze
from slopgate.stats.recovery.chains import (
    ChainState,
    ChainStatus,
    build_chains,
    recovery_rate,
    summarize_chains,
)
from slopgate.stats.recovery.normalization import normalize_entries
from slopgate.stats.recovery.rule_metrics import recovery_report


@dataclass(frozen=True, slots=True)
class _EventSpec:
    evaluation_id: str
    timestamp: str
    event_name: str = "PreToolUse"
    event_outcome: str = "passed_clean"
    tool_outcome: str = "unknown"
    fingerprint: str | None = None
    path: str | None = "src/app.py"
    repo: str = "/repo-a"
    findings: tuple[ObjectDict, ...] = ()
    mutating: bool = True


def _finding(rule_id: str) -> ObjectDict:
    return {
        "rule_id": rule_id,
        METADATA_DECISION: "deny",
        "severity": "HIGH",
        "message": f"{rule_id} triggered",
        "metadata": {"path": "src/app.py"},
    }


def _event(spec: _EventSpec) -> ObjectDict:
    return {
        "timestamp": spec.timestamp,
        "trace_schema_version": 2,
        "evaluation_id": spec.evaluation_id,
        "operation_id": None,
        "correlation_confidence": "inferred",
        "event_name": spec.event_name,
        "event_outcome": spec.event_outcome,
        "tool_outcome": spec.tool_outcome,
        "session_id": "session-1",
        "tool_name": "Edit",
        "candidate_paths": [spec.path] if spec.path is not None else [],
        "attempt_fingerprint": spec.fingerprint,
        "resolved_repo_root": spec.repo,
        "enforcement_mode": "repo_strict",
        "platform_capability": "full",
        "rule_response_version": "1",
        "intervention_tags": [],
        "repair_plan_state": "none",
        "mutating": spec.mutating,
        "findings": list(spec.findings),
        "errors": [],
    }


_DENIAL = _event(
    _EventSpec(
        evaluation_id="deny-1",
        timestamp="2026-07-14T12:00:00+00:00",
        event_outcome="blocked_pre_tool",
        fingerprint="a",
        findings=(_finding("RULE-001"),),
    )
)
_TERMINAL = _event(
    _EventSpec(
        evaluation_id="stop-1",
        timestamp="2026-07-14T12:01:00+00:00",
        event_name="Stop",
        path=None,
        mutating=False,
    )
)
_CHANGED_RETRY = _event(
    _EventSpec(
        evaluation_id="retry-1",
        timestamp="2026-07-14T12:01:00+00:00",
        fingerprint="b",
    )
)
_SUCCESSFUL_POST_TOOL = _event(
    _EventSpec(
        evaluation_id="post-1",
        timestamp="2026-07-14T12:02:00+00:00",
        event_name="PostToolUse",
        tool_outcome="success",
        fingerprint="b",
    )
)
_FAILED_POST_TOOL = _event(
    _EventSpec(
        evaluation_id="post-failed",
        timestamp="2026-07-14T12:01:30+00:00",
        event_name="PostToolUse",
        event_outcome="tool_failed",
        tool_outcome="failure",
        fingerprint="a",
    )
)
_SAME_FINGERPRINT_DENIAL = _event(
    _EventSpec(
        evaluation_id="same-deny",
        timestamp="2026-07-14T12:00:00+00:00",
        event_outcome="blocked_pre_tool",
        fingerprint="same",
        findings=(_finding("RULE-001"),),
    )
)
_SAME_FINGERPRINT_RETRY = _event(
    _EventSpec(
        evaluation_id="same-retry",
        timestamp="2026-07-14T12:01:00+00:00",
        event_outcome="blocked_pre_tool",
        fingerprint="same",
        findings=(_finding("RULE-001"),),
    )
)
_OTHER_REPOSITORY_DENIAL = _event(
    _EventSpec(
        evaluation_id="deny-b",
        timestamp="2026-07-14T12:01:00+00:00",
        repo="/repo-b",
        event_outcome="blocked_pre_tool",
        findings=(_finding("RULE-001"),),
    )
)
_OTHER_RULE_RETRY = _event(
    _EventSpec(
        evaluation_id="other-rule-retry",
        timestamp="2026-07-14T12:01:00+00:00",
        event_outcome="blocked_pre_tool",
        fingerprint="b",
        findings=(_finding("RULE-002"),),
    )
)


def _session_event(
    event: ObjectDict, session_id: str, evaluation_id: str
) -> ObjectDict:
    return {**event, "session_id": session_id, "evaluation_id": evaluation_id}


_FRICTION_ORDER_ENTRIES = (
    {
        **_session_event(_DENIAL, "friction-session", "friction-denial"),
        "findings": [_finding("RULE-FRICTION")],
    },
    _session_event(_FAILED_POST_TOOL, "friction-session", "friction-failed"),
    _session_event(_TERMINAL, "friction-session", "friction-terminal"),
    {
        **_session_event(_DENIAL, "healthy-session-1", "healthy-denial-1"),
        "findings": [_finding("RULE-HEALTHY")],
    },
    _session_event(_SUCCESSFUL_POST_TOOL, "healthy-session-1", "healthy-success-1"),
    {
        **_session_event(_DENIAL, "healthy-session-2", "healthy-denial-2"),
        "findings": [_finding("RULE-HEALTHY")],
    },
    _session_event(_SUCCESSFUL_POST_TOOL, "healthy-session-2", "healthy-success-2"),
)


def test_terminal_event_marks_unrecovered_chain_abandoned() -> None:
    recovery = object_dict(analyze([_DENIAL, _TERMINAL]).get("recovery"))

    assert object_dict(recovery.get("summary")) == {
        "chains": 1,
        "recovered": 0,
        "abandoned": 1,
        "open_censored": 0,
    }, "Only an explicit terminal event may mark the chain abandoned"


def test_denial_at_window_end_remains_open_censored() -> None:
    recovery = object_dict(analyze([_DENIAL]).get("recovery"))

    assert object_dict(recovery.get("summary")) == {
        "chains": 1,
        "recovered": 0,
        "abandoned": 0,
        "open_censored": 1,
    }, "Silence at the data boundary must remain open/censored"


def test_allowed_pretool_retry_clears_original_rule() -> None:
    recovery = object_dict(analyze([_DENIAL, _CHANGED_RETRY]).get("recovery"))
    rates = object_dict(recovery.get("rates"))

    assert object_dict(rates.get("first_retry_rule_clearance")) == {
        "numerator": 1,
        "denominator": 1,
        "percentage": 100.0,
    }, "A pre-tool allow must count as original-rule clearance"


def test_allowed_pretool_retry_does_not_claim_operation_success() -> None:
    recovery = object_dict(analyze([_DENIAL, _CHANGED_RETRY]).get("recovery"))
    rates = object_dict(recovery.get("rates"))

    assert object_dict(rates.get("first_retry_operation_success")) == {
        "numerator": 0,
        "denominator": 0,
        "percentage": None,
    }, "A pre-tool allow cannot prove that the tool operation succeeded"


def test_successful_same_path_posttool_recovers_chain() -> None:
    recovery = object_dict(analyze([_DENIAL, _SUCCESSFUL_POST_TOOL]).get("recovery"))

    assert object_dict(recovery.get("summary")) == {
        "chains": 1,
        "recovered": 1,
        "abandoned": 0,
        "open_censored": 0,
    }, "Observed successful same-target completion must recover the chain"


def test_successful_posttool_with_blocking_finding_stays_open() -> None:
    blocked_post_tool = {
        **_SUCCESSFUL_POST_TOOL,
        "event_outcome": "blocked_post_tool",
        "findings": [_finding("RULE-002")],
    }
    recovery = object_dict(analyze([_DENIAL, blocked_post_tool]).get("recovery"))

    assert object_dict(recovery.get("summary")) == {
        "chains": 2,
        "recovered": 0,
        "abandoned": 0,
        "open_censored": 2,
    }, "A successful tool result with any blocking finding cannot prove recovery"


def test_same_first_retry_fingerprint_records_unchanged_retry() -> None:
    recovery = object_dict(
        analyze([_SAME_FINGERPRINT_DENIAL, _SAME_FINGERPRINT_RETRY]).get("recovery")
    )
    rates = object_dict(recovery.get("rates"))

    assert object_dict(rates.get("unchanged_first_retry")) == {
        "numerator": 1,
        "denominator": 1,
        "percentage": 100.0,
    }, "Identical fingerprints must record unchanged retry pressure"


def test_different_first_retry_fingerprint_records_changed_retry() -> None:
    recovery = object_dict(analyze([_DENIAL, _CHANGED_RETRY]).get("recovery"))
    rates = object_dict(recovery.get("rates"))

    assert object_dict(rates.get("changed_first_retry")) == {
        "numerator": 1,
        "denominator": 1,
        "percentage": 100.0,
    }, "Different fingerprints must record a materially changed retry"


def test_other_rule_blocking_after_clearance_flags_compound_friction() -> None:
    recovery = object_dict(analyze([_DENIAL, _OTHER_RULE_RETRY]).get("recovery"))
    rule = object_dict(object_list(recovery.get("rules"))[0])

    assert rule.get("classifications") == [
        "insufficient_telemetry",
        "compound_rule_friction",
    ], "A cleared original rule followed by another block must expose compound friction"


def test_identical_paths_in_different_repositories_do_not_correlate() -> None:
    recovery = object_dict(analyze([_DENIAL, _OTHER_REPOSITORY_DENIAL]).get("recovery"))
    summary = object_dict(recovery.get("summary"))

    assert summary.get("chains") == 2, (
        "Repository root must be part of recovery-chain identity"
    )


def test_build_chains_exposes_explicit_terminal_state() -> None:
    chains = build_chains(normalize_entries([_DENIAL, _TERMINAL]).events)
    chain: ChainState = chains[0]

    assert chain.status is ChainStatus.ABANDONED, (
        "The typed chain seam must preserve explicit abandonment"
    )


def test_recovery_rate_and_summary_preserve_units() -> None:
    chains = build_chains(normalize_entries([_DENIAL]).events)
    summary = object_dict(summarize_chains(chains).get("summary"))

    assert (recovery_rate(1, 2), summary.get("open_censored")) == (
        {"numerator": 1, "denominator": 2, "percentage": 50.0},
        1,
    ), "Shared recovery seams must retain explicit units and censoring"


def test_recovery_report_exposes_rule_metrics() -> None:
    batch = normalize_entries([_DENIAL])

    report = recovery_report(batch.events, batch.duplicate_records_removed)

    assert len(object_list(report.get("rules"))) == 1, (
        "The rule report seam must expose one row per rule variant"
    )


def test_recovery_report_ranks_friction_before_raw_chain_volume() -> None:
    recovery = object_dict(analyze(list(_FRICTION_ORDER_ENTRIES)).get("recovery"))
    rules = object_list(recovery.get("rules"))

    assert object_dict(rules[0]).get("rule_id") == "RULE-FRICTION", (
        "Recovery friction must outrank a larger volume of healthy chains"
    )
