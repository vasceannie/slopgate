"""Scope model primitives for improvement measurement.

Families, path normalization, and the parsed result record live here so the
episode evaluator stays small and the dashboard mirror can port this file
one-to-one.
"""

from __future__ import annotations

import posixpath
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone

from slopgate.constants import BASH_TOOL_LOWER, UNKNOWN_VALUE

UNKNOWN_POLICY = "unknown_policy"
UNKNOWN_VERSION = "unknown_version"
PATHLESS_SENTINEL = "__pathless__"

STRICT_MODE = "repo_strict"
RELAXED_MODE = "repo_relaxed"
OUTSIDE_MODE = "outside_repo"

ENFORCING_DECISIONS = frozenset({"deny", "block"})

STATE_RESOLVED = "resolved"
STATE_STILL_FAILING = "still_failing"
STATE_NO_FOLLOWUP = "no_observed_followup"
STATE_PROVENANCE_CHANGED = "provenance_changed"
STATE_EVALUATION_ERROR = "evaluation_error"
EPISODE_TERMINAL_STATES = (
    STATE_RESOLVED,
    STATE_STILL_FAILING,
    STATE_NO_FOLLOWUP,
    STATE_PROVENANCE_CHANGED,
    STATE_EVALUATION_ERROR,
)

FILE_MUTATION_TOOLS = frozenset(
    {
        "write",
        "edit",
        "multiedit",
        "notebookedit",
        "apply_patch",
        "applypatch",
    }
)
SHELL_TOOLS = frozenset({BASH_TOOL_LOWER, "powershell"})
SEARCH_TOOLS = frozenset({"glob", "grep"})
WEB_TOOLS = frozenset({"webfetch", "websearch", "web_fetch", "web_search"})
LIFECYCLE_NAMES = frozenset(
    {"stop", "sessionend", "subagentstop", "subagentstart", "sessionstart"}
)
TOOL_FAMILIES = (
    ("file_mutation", FILE_MUTATION_TOOLS),
    ("shell", SHELL_TOOLS),
    ("search", SEARCH_TOOLS),
    ("web", WEB_TOOLS),
    ("lifecycle", LIFECYCLE_NAMES),
)

StructuralKey = tuple[str, str, str, tuple[str, ...]]
ProvenanceKey = tuple[str, str, str, str]


def semantic_tool_family(tool_name: object, event_name: object) -> str:
    """Map a canonical tool/event pair onto a narrow semantic family."""
    tool = str(tool_name or "").strip().lower()
    for family, members in TOOL_FAMILIES:
        if tool in members:
            return family
    event = str(event_name or "").strip().lower()
    if not tool and event in LIFECYCLE_NAMES:
        return "lifecycle"
    return "other"


def normalize_target_path(raw: str, repo_root: str | None) -> str:
    """Normalize one path for scope identity.

    Separators become POSIX, ``.`` and ``..`` resolve, in-repo paths become
    repo-relative, and anything else stays a normalized absolute path.
    """
    path = posixpath.normpath(raw.replace("\\", "/"))
    if repo_root:
        root = posixpath.normpath(repo_root.replace("\\", "/"))
        if path == root:
            return "."
        if path.startswith(root + "/"):
            return path[len(root) + 1 :]
    return path


def normalized_path_set(
    raw_paths: Sequence[object], repo_root: str | None
) -> tuple[str, ...]:
    """Return the deduplicated sorted normalized form of raw paths."""
    normalized = {
        normalize_target_path(str(item), repo_root)
        for item in raw_paths
        if str(item or "").strip()
    }
    normalized.discard("")
    return tuple(sorted(normalized))


def parse_timestamp(raw: object) -> datetime | None:
    """Parse an ISO timestamp, tolerating missing or malformed values."""
    text = str(raw or "")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def timestamp_key(raw: object) -> tuple[int, str]:
    """Return a sortable key that places parseable timestamps first."""
    text = str(raw or "")
    parsed = parse_timestamp(text)
    if parsed is None:
        return (1, text)
    aware = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return (0, aware.astimezone(timezone.utc).isoformat())


def optional_str(value: object) -> str | None:
    """Return the value as a non-empty string or None."""
    if isinstance(value, str) and value:
        return value
    return None


@dataclass(slots=True)
class ResultRecord:
    """One parsed ``results.jsonl`` row used by the improvement model."""

    index: int
    session: str
    timestamp: str
    event_name: str
    tool_name: str
    family: str
    mutating: bool
    repo_root: str | None
    enforcement_mode: str
    platform: str
    platform_capability: str | None
    model: str | None
    provider: str | None
    target_paths: tuple[str, ...]
    candidate_paths: tuple[str, ...]
    languages: tuple[str, ...]
    slopgate_version: str | None
    policy_fingerprint: str | None
    guidance_fingerprint: str | None
    blocking_rules: tuple[str, ...]
    errored_rules: frozenset[str]
    has_errors: bool
    evaluation_ms: float | None
    rule_engine_ms: float | None
    paths_from_findings: bool = field(default=False)
    rule_target_paths: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def legacy(self) -> bool:
        return (
            self.policy_fingerprint is None
            or self.guidance_fingerprint is None
            or self.slopgate_version is None
        )

    @property
    def pathless(self) -> bool:
        return self.target_paths == (PATHLESS_SENTINEL,)

    @property
    def scope_confidence(self) -> str:
        if self.pathless:
            return "low"
        return "high" if self.paths_from_findings else "medium"

    @property
    def structural_key(self) -> StructuralKey:
        return (self.session, self.repo_root or "", self.family, self.target_paths)

    def structural_key_for_rule(self, rule_id: str) -> StructuralKey:
        paths = self.rule_target_paths.get(rule_id, self.target_paths)
        return (self.session, self.repo_root or "", self.family, paths)

    @property
    def cohort_key(self) -> tuple[StructuralKey, ProvenanceKey]:
        return (self.structural_key, self.provenance_key)

    @property
    def provenance_key(self) -> ProvenanceKey:
        return (
            self.enforcement_mode,
            self.slopgate_version or UNKNOWN_VERSION,
            self.policy_fingerprint or UNKNOWN_POLICY,
            self.guidance_fingerprint or UNKNOWN_POLICY,
        )


@dataclass(slots=True)
class RepairEpisode:
    """One block-anchored rule-local repair lifecycle."""

    rule_id: str
    anchor: ResultRecord
    state: str = STATE_NO_FOLLOWUP
    followups: int = 0
    last_enforcing: bool = False
    last_error: bool = False
    provenance_divergence: bool = False
    resolved_record: ResultRecord | None = None

    @property
    def attempts(self) -> int:
        return self.followups if self.resolved_record is not None else 0

    @property
    def latency_ms(self) -> float | None:
        if self.resolved_record is None:
            return None
        start = parse_timestamp(self.anchor.timestamp)
        end = parse_timestamp(self.resolved_record.timestamp)
        if start is None or end is None:
            return None
        delta = end - start
        return round(delta.total_seconds() * 1000.0, 1)


@dataclass(slots=True)
class EpisodeEvaluation:
    """All model outputs for one window of result rows."""

    records: list[ResultRecord]
    episodes: list[RepairEpisode]
    rule_followups: dict[str, int]
    rule_enforcing_followups: dict[str, int]
    first_observed: list[ResultRecord]


__all__ = ["UNKNOWN_VALUE"]


def __getattr__(name: str) -> object:
    """Lazily preserve the historical parser export without a cycle."""
    if name == "parse_result_record":
        from .parsing import parse_result_record

        return parse_result_record
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
