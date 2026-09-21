"""Offline evaluation of redacted L1 attempt-case packs."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path

from slopgate._types import ObjectDict, object_dict
from slopgate.engine import evaluate_payload

_PRETOOL_EVENTS = frozenset({"PreToolUse", "tool.execute.before"})
_FILE_MUTATION_TOOLS = frozenset(
    {
        "Write",
        "Edit",
        "MultiEdit",
        "apply_patch",
        "ApplyPatch",
        "replace",
        "edit",
        "write",
    }
)


def load_eval_cases(path: Path | str) -> list[ObjectDict]:
    """Load JSONL attempt cases (slopdata L1 or pinned holdout)."""
    cases: list[ObjectDict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parsed = object_dict(json.loads(line))
        if parsed:
            cases.append(parsed)
    return cases


def _finding_rule_ids(result: object) -> list[str]:
    findings = getattr(result, "findings", None) or []
    rules: list[str] = []
    for finding in findings:
        rule_id = getattr(finding, "rule_id", None)
        if rule_id is None and isinstance(finding, dict):
            rule_id = finding.get("rule_id")
        if rule_id and str(rule_id) not in rules:
            rules.append(str(rule_id))
    return rules


def case_is_replayable(case: ObjectDict) -> bool:
    """True for PreToolUse cases with non-empty input (and paths for mutations)."""
    tier = case.get("tier")
    if tier == "replayable":
        return True
    if tier == "label_only":
        return False
    payload = object_dict(case.get("replay_payload")) or {}
    event = str(case.get("event_name") or payload.get("hook_event_name") or "")
    if event not in _PRETOOL_EVENTS:
        return False
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict) or not tool_input:
        return False
    tool_name = str(case.get("tool_name") or payload.get("tool_name") or "")
    if tool_name in _FILE_MUTATION_TOOLS:
        paths = case.get("redacted_paths") or []
        file_path = (
            tool_input.get("file_path")
            or tool_input.get("filePath")
            or tool_input.get("path")
            or tool_input.get("patch")
            or tool_input.get("patchText")
            or tool_input.get("patch_text")
            or tool_input.get("content")
        )
        if not paths and not file_path:
            return False
    return True


def overlay_row_from_eval(
    case: ObjectDict,
    result: ObjectDict,
    *,
    engine_version: str,
    cwd_kind: str = "enrolled_temp",
    evaluated_at: str | None = None,
    schema_version: int = 1,
) -> ObjectDict:
    """Sidecar row keyed by ``case_id``. Does not mutate historical ``expected``."""
    current = [str(item) for item in (result.get("got_rules") or [])]
    return {
        "schema_version": schema_version,
        "case_id": case.get("case_id"),
        "engine_version": engine_version,
        "evaluated_at": evaluated_at
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cwd_kind": cwd_kind,
        "current_rules": current,
        "primary_rule_current": current[0] if current else "_CLEAN",
        "primary_hit": bool(result.get("primary_hit")),
        "exact_match": bool(result.get("exact_rule_set_match")),
        "error": result.get("error"),
        "replayable": bool(result.get("replayable")),
    }


def write_overlay_jsonl(path: Path | str, rows: Sequence[ObjectDict]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def evaluate_case(case: ObjectDict, *, cwd: str | None = None) -> ObjectDict:
    """Replay one case through ``evaluate_payload`` and compare rule sets."""
    payload = object_dict(case.get("replay_payload")) or {}
    if cwd:
        payload = dict(payload)
        payload["cwd"] = cwd
    platform = str(case.get("platform") or "claude")
    expected = [
        str(item.get("rule_id"))
        for item in (case.get("expected") or [])
        if isinstance(item, dict) and item.get("rule_id")
    ]
    expected_unique: list[str] = []
    for rule_id in expected:
        if rule_id not in expected_unique:
            expected_unique.append(rule_id)

    error: str | None = None
    got: list[str] = []
    try:
        result = evaluate_payload(payload, platform=platform)
        got = _finding_rule_ids(result)
    except Exception as exc:  # noqa: BLE001 — eval reports failures
        error = f"{type(exc).__name__}: {exc}"

    overlap = sorted(set(got) & set(expected_unique))
    primary = str(case.get("primary_rule") or "")
    true_negative = case.get("label_kind") == "true_negative" or primary == "_CLEAN"
    if true_negative:
        exact = not got and error is None
        primary_hit = exact
    else:
        exact = got == expected_unique
        primary_hit = bool(primary and primary in got)
    return {
        "case_id": case.get("case_id"),
        "platform": platform,
        "primary_rule": case.get("primary_rule"),
        "expected_rules": expected_unique,
        "got_rules": got,
        "overlap": overlap,
        "exact_rule_set_match": exact,
        "any_overlap": bool(overlap) or (true_negative and exact),
        "primary_hit": primary_hit,
        "error": error,
        "replayable": case_is_replayable(case),
    }


def summarize_eval(results: Sequence[ObjectDict]) -> ObjectDict:
    """Aggregate per-case eval rows into a compact report."""
    n = len(results)
    by_rule = Counter(
        str(row.get("primary_rule") or "_none") for row in results
    )
    return {
        "n": n,
        "exact_matches": sum(1 for row in results if row.get("exact_rule_set_match")),
        "any_overlap": sum(1 for row in results if row.get("any_overlap")),
        "primary_hits": sum(1 for row in results if row.get("primary_hit")),
        "errors": sum(1 for row in results if row.get("error")),
        "by_primary_rule": by_rule.most_common(),
        "note": (
            "Historical labels may diverge from current policy; use as a "
            "regression smoke signal, not a hard quality gate."
        ),
    }


def evaluate_pack(
    path: Path | str,
    *,
    limit: int | None = None,
    replayable_only: bool = True,
    cwd: str | None = None,
    overlay_out: Path | str | None = None,
    engine_version: str | None = None,
    cwd_kind: str = "as_payload",
) -> ObjectDict:
    """Load, evaluate, and summarize an L1 JSONL pack.

    ``replayable_only`` (default) skips label_only rows so empty-input
    lifecycle cases are not treated as a quality gate.
    """
    cases = load_eval_cases(path)
    skipped = 0
    if replayable_only:
        filtered = [case for case in cases if case_is_replayable(case)]
        skipped = len(cases) - len(filtered)
        cases = filtered
    if limit is not None:
        cases = cases[:limit]
    rows = [evaluate_case(case, cwd=cwd) for case in cases]
    summary = summarize_eval(rows)
    summary["results"] = list(rows)
    summary["pack"] = str(path)
    summary["replayable_only"] = replayable_only
    summary["skipped_label_only"] = skipped
    if overlay_out is not None:
        from slopgate import __version__ as installed_version

        version = engine_version or str(installed_version)
        overlay_rows = [
            overlay_row_from_eval(
                case,
                result,
                engine_version=version,
                cwd_kind=cwd_kind if cwd else "as_payload",
            )
            for case, result in zip(cases, rows, strict=True)
        ]
        write_overlay_jsonl(overlay_out, overlay_rows)
        summary["overlay_out"] = str(overlay_out)
        summary["overlay_rows"] = len(overlay_rows)
    return summary


def iter_case_ids(results: Iterable[ObjectDict]) -> list[str]:
    return [str(row.get("case_id")) for row in results if row.get("case_id")]
