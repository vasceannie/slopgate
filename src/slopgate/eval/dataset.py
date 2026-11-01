"""Offline evaluation of redacted L1 attempt-case packs."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from slopgate._types import ObjectDict, object_dict
from slopgate.constants import (
    EDIT_TOOL_NAMES,
    ERROR_KEY,
    EVENT_NAME_KEY,
    HOOK_EVENT_NAME_KEY,
    METADATA_CONTENT,
    METADATA_CWD,
    METADATA_PATH,
    METADATA_TOOL_NAME,
    PATCH_BLOB_KEYS,
    PLATFORM_CLAUDE,
    PLATFORM_KEY,
    PRE_TOOL_USE,
    REPLACE,
    RULE_ID_KEY,
)
from slopgate.engine import evaluate_payload
from slopgate.util import warning

from .overlay import (
    CLEAN_PRIMARY_RULE,
    OverlayProvenance,
    overlay_row_from_eval,
    write_overlay_jsonl,
)

_PRETOOL_EVENTS = frozenset({PRE_TOOL_USE, "tool.execute.before"})
_FILE_MUTATION_TOOLS = EDIT_TOOL_NAMES | {REPLACE}
_MUTATION_TARGET_KEYS = (
    "file_path",
    "filePath",
    METADATA_PATH,
    *PATCH_BLOB_KEYS,
    METADATA_CONTENT,
)
_DECLARED_TIER_REPLAYABILITY = {"replayable": True, "label_only": False}
AS_PAYLOAD_CWD_KIND = "as_payload"
OVERLAY_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
# Rule errors are captured inside the engine, so these are the replay failures
# left: bad platform or payload shapes, and unreadable config, state, or logs.
_REPLAY_FAILURES = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


@dataclass(frozen=True, slots=True)
class OverlayOutput:
    """Where to write a pack's overlay sidecar and how to label its rows."""

    path: Path | str
    engine_version: str | None = None
    cwd_kind: str = AS_PAYLOAD_CWD_KIND


@dataclass(frozen=True, slots=True)
class EvalPackOptions:
    """Case selection and output settings for one pack evaluation.

    ``replayable_only`` (default) skips label_only rows so empty-input
    lifecycle cases are not treated as a quality gate.
    """

    limit: int | None = None
    replayable_only: bool = True
    cwd: str | None = None
    overlay: OverlayOutput | None = None


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
        rule_id = getattr(finding, RULE_ID_KEY, None)
        if rule_id is None and isinstance(finding, dict):
            rule_id = finding.get(RULE_ID_KEY)
        if rule_id and str(rule_id) not in rules:
            rules.append(str(rule_id))
    return rules


def _has_mutation_target(case: ObjectDict, tool_input: ObjectDict) -> bool:
    if case.get("redacted_paths"):
        return True
    return any(tool_input.get(key) for key in _MUTATION_TARGET_KEYS)


def case_is_replayable(case: ObjectDict) -> bool:
    """True for PreToolUse cases with non-empty input (and paths for mutations)."""
    declared = _DECLARED_TIER_REPLAYABILITY.get(str(case.get("tier")))
    if declared is not None:
        return declared
    payload = object_dict(case.get("replay_payload")) or {}
    event = case.get(EVENT_NAME_KEY) or payload.get(HOOK_EVENT_NAME_KEY)
    if str(event or "") not in _PRETOOL_EVENTS:
        return False
    tool_input = object_dict(payload.get("tool_input"))
    if not tool_input:
        return False
    tool_name = case.get(METADATA_TOOL_NAME) or payload.get(METADATA_TOOL_NAME)
    if str(tool_name or "").lower() not in _FILE_MUTATION_TOOLS:
        return True
    return _has_mutation_target(case, tool_input)


def _expected_rule_ids(case: ObjectDict) -> list[str]:
    items = case.get("expected")
    rule_ids = [
        str(item.get(RULE_ID_KEY))
        for item in (items if isinstance(items, list) else [])
        if isinstance(item, dict) and item.get(RULE_ID_KEY)
    ]
    return list(dict.fromkeys(rule_ids))


def _replay_rule_ids(
    case: ObjectDict, platform: str, cwd: str | None
) -> tuple[list[str], str | None]:
    """Replay one case, reporting a failure as data so the pack keeps running."""
    payload = object_dict(case.get("replay_payload")) or {}
    if cwd:
        payload = {**payload, METADATA_CWD: cwd}
    try:
        return _finding_rule_ids(evaluate_payload(payload, platform=platform)), None
    except _REPLAY_FAILURES as exc:
        error_type = type(exc).__name__
        warning("eval case replay failed", case_id=case.get("case_id"), error_type=error_type)
        return [], f"{error_type}: {exc}"


def evaluate_case(case: ObjectDict, *, cwd: str | None = None) -> ObjectDict:
    """Replay one case through ``evaluate_payload`` and compare rule sets."""
    platform = str(case.get(PLATFORM_KEY) or PLATFORM_CLAUDE)
    expected = _expected_rule_ids(case)
    got, error = _replay_rule_ids(case, platform, cwd)
    overlap = sorted(set(got) & set(expected))
    primary = str(case.get("primary_rule") or "")
    true_negative = (
        case.get("label_kind") == "true_negative" or primary == CLEAN_PRIMARY_RULE
    )
    if true_negative:
        exact = not got and error is None
        primary_hit = exact
    else:
        exact = got == expected
        primary_hit = bool(primary and primary in got)
    return {
        "case_id": case.get("case_id"),
        PLATFORM_KEY: platform,
        "primary_rule": case.get("primary_rule"),
        "expected_rules": expected,
        "got_rules": got,
        "overlap": overlap,
        "exact_rule_set_match": exact,
        "any_overlap": bool(overlap) or (true_negative and exact),
        "primary_hit": primary_hit,
        ERROR_KEY: error,
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
        "errors": sum(1 for row in results if row.get(ERROR_KEY)),
        "by_primary_rule": by_rule.most_common(),
        "note": (
            "Historical labels may diverge from current policy; use as a "
            "regression smoke signal, not a hard quality gate."
        ),
    }


def _select_cases(
    cases: list[ObjectDict], options: EvalPackOptions
) -> tuple[list[ObjectDict], int]:
    """Return the cases to evaluate and how many label-only rows were skipped."""
    selected = cases
    if options.replayable_only:
        selected = [case for case in cases if case_is_replayable(case)]
    skipped = len(cases) - len(selected)
    if options.limit is not None:
        selected = selected[: options.limit]
    return selected, skipped


def _write_pack_overlay(
    cases: Sequence[ObjectDict], rows: Sequence[ObjectDict], options: EvalPackOptions
) -> ObjectDict:
    """Write the sidecar for this run and return its summary fields."""
    overlay = options.overlay
    if overlay is None:
        return {}
    from slopgate import __version__

    provenance = OverlayProvenance(
        engine_version=overlay.engine_version or __version__,
        evaluated_at=datetime.now(timezone.utc).strftime(OVERLAY_TIMESTAMP_FORMAT),
        cwd_kind=overlay.cwd_kind if options.cwd else AS_PAYLOAD_CWD_KIND,
    )
    overlay_rows = [
        overlay_row_from_eval(case, result, provenance)
        for case, result in zip(cases, rows, strict=True)
    ]
    write_overlay_jsonl(overlay.path, overlay_rows)
    return {"overlay_out": str(overlay.path), "overlay_rows": len(overlay_rows)}


def evaluate_pack(
    path: Path | str, options: EvalPackOptions | None = None
) -> ObjectDict:
    """Load, evaluate, and summarize an L1 JSONL pack."""
    pack_options = options or EvalPackOptions()
    cases, skipped = _select_cases(load_eval_cases(path), pack_options)
    rows = [evaluate_case(case, cwd=pack_options.cwd) for case in cases]
    return {
        **summarize_eval(rows),
        "results": list(rows),
        "pack": str(path),
        "replayable_only": pack_options.replayable_only,
        "skipped_label_only": skipped,
        **_write_pack_overlay(cases, rows, pack_options),
    }


def iter_case_ids(results: Iterable[ObjectDict]) -> list[str]:
    return [str(row.get("case_id")) for row in results if row.get("case_id")]
