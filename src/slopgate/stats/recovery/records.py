"""Typed records used by deterministic recovery analytics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from slopgate.constants import (
    ALLOW,
    ASK,
    BLOCK,
    CONTEXT,
    DENY,
    INFO,
    METADATA_COMMAND,
    UNKNOWN_VALUE,
    WARN,
)


class EventOutcome(str, Enum):
    """Mutually exclusive completed-result classifications."""

    BLOCKED_PRE_TOOL = "blocked_pre_tool"
    BLOCKED_POST_TOOL = "blocked_post_tool"
    ASKED = "asked"
    PASSED_WITH_ADVISORY = "passed_with_advisory"
    PASSED_CLEAN = "passed_clean"
    TOOL_FAILED = "tool_failed"
    EVALUATION_ERROR = "evaluation_error"
    UNKNOWN = UNKNOWN_VALUE


class FindingDecision(str, Enum):
    """Finding-level decisions with no synthetic event allow."""

    DENY = DENY
    BLOCK = BLOCK
    ASK = ASK
    WARN = WARN
    CONTEXT = CONTEXT
    INFO = INFO
    ALLOW = ALLOW
    NO_EXPLICIT_DECISION = "no_explicit_decision"


class CorrelationConfidence(str, Enum):
    """Evidence strength used to correlate attempts."""

    EXACT = "exact"
    INFERRED = "inferred"
    UNAVAILABLE = "unavailable"


class ToolOutcome(str, Enum):
    """Observed tool execution outcome, independent of policy decisions."""

    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = UNKNOWN_VALUE


class RepairPlanState(str, Enum):
    """Structured repair-plan intervention state."""

    NONE = "none"
    REQUESTED = "requested"
    OBSERVED = "observed"


class TargetType(str, Enum):
    """Comparable recovery-target categories."""

    FILE = "file"
    COMMAND = METADATA_COMMAND
    REPOSITORY = "repository"
    SESSION = "session"
    UNKNOWN = UNKNOWN_VALUE


@dataclass(frozen=True, slots=True)
class RecoveryTarget:
    """A normalized target whose type prevents invalid chain correlation."""

    target_type: TargetType
    value: str


@dataclass(frozen=True, slots=True)
class NormalizedFinding:
    """One finding decision normalized from a completed result record."""

    source_finding_index: int
    rule_id: str
    rule_variant: str | None
    decision: FindingDecision
    severity: str
    message: str
    targets: tuple[RecoveryTarget, ...]

    @property
    def label(self) -> str:
        """Return the stable rule/variant report label."""
        if self.rule_variant is None:
            return self.rule_id
        return f"{self.rule_id} / {self.rule_variant}"

    @property
    def is_blocking(self) -> bool:
        """Return whether this finding prevented or blocked work."""
        return self.decision in {FindingDecision.DENY, FindingDecision.BLOCK}


@dataclass(frozen=True, slots=True)
class NormalizedEvent:
    """One deduplicated completed Slopgate evaluation."""

    source_index: int
    timestamp: str
    trace_schema_version: int | None
    evaluation_id: str | None
    operation_id: str | None
    correlation_confidence: CorrelationConfidence
    session_id: str
    event_name: str
    event_outcome: EventOutcome
    tool_name: str
    tool_outcome: ToolOutcome
    candidate_paths: tuple[str, ...]
    attempt_fingerprint: str | None
    resolved_repo_root: str | None
    enforcement_mode: str
    platform_capability: str
    rule_response_version: str | None
    intervention_tags: tuple[str, ...]
    repair_plan_state: RepairPlanState
    findings: tuple[NormalizedFinding, ...]
    is_legacy: bool

    def distinct_findings(self) -> tuple[NormalizedFinding, ...]:
        """Collapse rule-variant fanout back to raw finding units."""
        unique: dict[int, NormalizedFinding] = {}
        for finding in self.findings:
            unique.setdefault(finding.source_finding_index, finding)
        return tuple(unique.values())


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    """Normalized events plus explicit ingestion and coverage accounting."""

    events: tuple[NormalizedEvent, ...]
    raw_total_events: int
    fixture_filtered: int
    duplicate_records_removed: int
    legacy_schema_records: int
    trace_schema_versions_seen: tuple[int, ...]
