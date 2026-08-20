"""Parsing of result trace rows into the improvement scope model."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from slopgate._types import ObjectDict, object_dict, object_list
from slopgate.constants import SESSION_ID, UNKNOWN_VALUE
from slopgate.util.metadata_paths import effective_metadata_path, metadata_hit_paths

from .scope_model import (
    ENFORCING_DECISIONS,
    PATHLESS_SENTINEL,
    ResultRecord,
    normalized_path_set,
    optional_str,
    semantic_tool_family,
)


def _parse_blocking_findings(
    findings_raw: object, repo_root: str | None
) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, tuple[str, ...]]]:
    blocking: list[str] = []
    implicated: list[str] = []
    rule_implicated: dict[str, list[str]] = {}
    for finding_raw in object_list(findings_raw):
        finding = object_dict(finding_raw)
        if not finding or finding.get("decision") not in ENFORCING_DECISIONS:
            continue
        rule_id = str(finding.get("rule_id", UNKNOWN_VALUE))
        if rule_id not in blocking:
            blocking.append(rule_id)
        paths: list[str] = []
        _collect_finding_paths(finding.get("metadata"), paths)
        _collect_finding_paths(finding.get("metadata"), implicated)
        if paths:
            rule_implicated.setdefault(rule_id, []).extend(paths)
    normalized_rules = {
        rule_id: normalized_path_set(paths, repo_root)
        for rule_id, paths in rule_implicated.items()
    }
    return tuple(blocking), normalized_path_set(implicated, repo_root), normalized_rules


def _collect_finding_paths(metadata: object, implicated: list[str]) -> None:
    path_value = effective_metadata_path(metadata)
    if path_value and path_value not in implicated:
        implicated.append(path_value)
    for hit in metadata_hit_paths(metadata):
        if hit not in implicated:
            implicated.append(hit)


def _error_rule_ids(errors: Sequence[str]) -> frozenset[str]:
    rules: set[str] = set()
    for error in errors:
        prefix, separator, _rest = error.partition(":")
        if separator and prefix.strip():
            rules.add(prefix.strip())
    return frozenset(rules)


def _timing_ms(entry: ObjectDict, key: str) -> float | None:
    raw = object_dict(entry.get("timing")).get(key)
    return float(raw) if isinstance(raw, (int, float)) else None


def _entry_errors(entry: ObjectDict) -> list[str]:
    return [str(item) for item in object_list(entry.get("errors")) if str(item).strip()]


def _select_target_paths(
    finding_paths: tuple[str, ...], candidate_paths: tuple[str, ...]
) -> tuple[tuple[str, ...], bool]:
    if finding_paths:
        return finding_paths, True
    if candidate_paths:
        return candidate_paths, False
    return (PATHLESS_SENTINEL,), False


def _rule_target_paths(
    rules: Sequence[str],
    finding_paths: dict[str, tuple[str, ...]],
    candidate_paths: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    return {
        rule_id: finding_paths.get(rule_id, candidate_paths) for rule_id in rules
    }


def parse_result_record(
    entry: Mapping[str, object], index: int
) -> ResultRecord | None:
    """Parse one result entry; fixture/test sessions return None."""
    session = str(entry.get(SESSION_ID, UNKNOWN_VALUE))
    if session.startswith("fixture-") or session.startswith("test-"):
        return None
    typed = object_dict(entry)
    repo_root = optional_str(typed.get("resolved_repo_root"))
    blocking_rules, finding_paths, rule_finding_paths = _parse_blocking_findings(
        typed.get("findings"), repo_root
    )
    candidate_paths = normalized_path_set(
        object_list(typed.get("candidate_paths")), repo_root
    )
    target_paths, from_findings = _select_target_paths(finding_paths, candidate_paths)
    errors = _entry_errors(typed)
    record = ResultRecord(
        index=index,
        session=session,
        timestamp=str(typed.get("timestamp", "")),
        event_name=str(typed.get("event_name", UNKNOWN_VALUE)),
        tool_name=str(typed.get("tool_name", "")),
        family=semantic_tool_family(typed.get("tool_name"), typed.get("event_name")),
        mutating=typed.get("mutating") is True,
        repo_root=repo_root,
        enforcement_mode=str(typed.get("enforcement_mode", UNKNOWN_VALUE)),
        platform=str(typed.get("platform", UNKNOWN_VALUE)),
        platform_capability=optional_str(typed.get("platform_capability")),
        model=optional_str(typed.get("model")),
        provider=optional_str(typed.get("provider")),
        target_paths=target_paths,
        candidate_paths=candidate_paths,
        languages=tuple(str(item) for item in object_list(typed.get("languages"))),
        slopgate_version=optional_str(typed.get("slopgate_version")),
        policy_fingerprint=optional_str(typed.get("effective_policy_fingerprint")),
        guidance_fingerprint=optional_str(typed.get("guidance_fingerprint")),
        blocking_rules=blocking_rules,
        errored_rules=_error_rule_ids(errors),
        has_errors=bool(errors),
        evaluation_ms=_timing_ms(typed, "evaluation_ms"),
        rule_engine_ms=_timing_ms(typed, "rule_engine_ms"),
        rule_target_paths=_rule_target_paths(
            blocking_rules, rule_finding_paths, candidate_paths
        ),
    )
    record.paths_from_findings = from_findings
    return record
