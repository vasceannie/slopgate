from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from slopgate._types import ObjectDict, object_list
from slopgate.constants import DENY, METADATA_PATH, PERMISSION_REQUEST, PRE_TOOL_USE
from slopgate.context import HookContext
from slopgate.models import RuleFinding, Severity
from slopgate.state import RetryLockPayload
from slopgate.util.payloads import is_edit_like_tool

from ._hints import (
    REPLAN_PROMPT,
    denial_context,
    failure_class,
    finding_path,
    retry_budget_relevant_denials,
    rule_hint,
)


def _normalize_attempt_path(ctx: HookContext, path_value: str) -> str:
    raw_path = Path(path_value)
    if raw_path.is_absolute():
        return str(raw_path.resolve(strict=False))
    return str((ctx.cwd / raw_path).resolve(strict=False))


def _stable_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _attempt_fingerprint(ctx: HookContext) -> str | None:
    if not is_edit_like_tool(ctx.tool_name):
        return None
    payload = {
        "tool_name": ctx.tool_name.lower(),
        "candidate_paths": sorted(
            {
                _normalize_attempt_path(ctx, path_value)
                for path_value in ctx.candidate_paths
                if path_value
            }
        ),
        "targets": sorted(
            {
                (
                    _normalize_attempt_path(ctx, target.path),
                    target.source,
                    hashlib.sha256(target.content.encode("utf-8")).hexdigest(),
                )
                for target in ctx.content_targets
                if target.path
            }
        ),
        "tool_input_hash": _stable_hash(ctx.tool_input),
    }
    if not payload["candidate_paths"] and not payload["targets"]:
        return None
    return _stable_hash(payload)


def _current_denied_rule_ids(findings: list[RuleFinding]) -> list[str]:
    return sorted({item.rule_id for item in retry_budget_relevant_denials(findings)})


def dedupe_findings(findings: list[RuleFinding]) -> list[RuleFinding]:
    unique_by_key = {
        (item.rule_id, item.decision, item.message, item.additional_context): item
        for item in reversed(findings)
    }
    return list(reversed(unique_by_key.values()))


def filter_search_reminder_dedupe(
    ctx: HookContext, findings: list[RuleFinding]
) -> list[RuleFinding]:
    reminder_indexes = [
        idx for idx, item in enumerate(findings) if item.rule_id == "REMIND-SEARCH-001"
    ]
    if not reminder_indexes:
        return findings
    if ctx.state.should_emit_search_reminder(ctx.session_id):
        ctx.state.record_search_reminder(ctx.session_id)
        first = reminder_indexes[0]
        return [
            item
            for idx, item in enumerate(findings)
            if item.rule_id != "REMIND-SEARCH-001" or idx == first
        ]
    return [item for item in findings if item.rule_id != "REMIND-SEARCH-001"]


def _record_denial_attempt(
    ctx: HookContext,
    item: RuleFinding,
    attempt_fingerprint: str | None,
) -> int:
    path_value = finding_path(item)
    state_path = _normalize_attempt_path(ctx, path_value) if path_value else None
    repeat_count = ctx.state.record_deny_hit(
        ctx.session_id,
        item.rule_id,
        state_path,
        attempt_fingerprint,
    )
    item.metadata["failure_class"] = failure_class(item.rule_id)
    item.metadata["repeat_count"] = repeat_count
    if attempt_fingerprint:
        item.metadata["attempt_fingerprint"] = attempt_fingerprint
    return repeat_count


def _apply_repeat_escalation(item: RuleFinding, repeat_count: int) -> bool:
    if repeat_count < 2:
        return False
    item.metadata["repeat_hit"] = True
    item.message = (
        (item.message or "").rstrip() + " Change design before retrying."
    ).strip()
    if repeat_count >= 3 and item.decision != "block":
        item.decision = "block"
        item.severity = max(item.severity, Severity.HIGH)
        item.metadata["escalated"] = True
    return True


def _repeat_denial_hints(
    ctx: HookContext,
    item: RuleFinding,
    repeat_count: int,
) -> list[str]:
    hints = [denial_context(ctx, item, repeat_count), REPLAN_PROMPT]
    hint = rule_hint(ctx, item)
    if hint:
        hints.append(hint)
    if repeat_count >= 2:
        hints.append(
            "Repeated deny detected: write a short repair plan before your next write."
        )
    return hints


def _append_denial_hints(item: RuleFinding, hints: list[str]) -> None:
    item.additional_context = "\n\n".join(
        part for part in [item.additional_context, *hints] if part
    )


def _retry_lock_paths(ctx: HookContext) -> list[str]:
    return sorted(
        {
            _normalize_attempt_path(ctx, path_value)
            for path_value in ctx.candidate_paths
            if path_value
        }
    )


def _clear_resolved_thin_wrapper_hits(
    ctx: HookContext,
    denied: list[RuleFinding],
) -> None:
    touched_paths = [target.path for target in ctx.content_targets if target.path]
    if not touched_paths:
        return
    found_pairs = {
        (
            item.rule_id,
            _normalize_attempt_path(ctx, path_value)
            if (path_value := finding_path(item)) is not None
            else "__pathless__",
        )
        for item in denied
    }
    for path in touched_paths:
        normalized = _normalize_attempt_path(ctx, path)
        for rule_id in ("PY-CODE-013",):
            key = (rule_id, normalized)
            if key not in found_pairs:
                ctx.state.clear_deny_hit(ctx.session_id, rule_id, normalized)


def apply_loop_aware_steering(ctx: HookContext, findings: list[RuleFinding]) -> None:
    denied = retry_budget_relevant_denials(findings)
    attempt_fingerprint = _attempt_fingerprint(ctx)
    current_rule_ids = _current_denied_rule_ids(findings)
    repeated_rule_ids: set[str] = set()
    max_repeat_count = 0
    for item in denied:
        repeat_count = _record_denial_attempt(ctx, item, attempt_fingerprint)
        max_repeat_count = max(max_repeat_count, repeat_count)
        if _apply_repeat_escalation(item, repeat_count):
            repeated_rule_ids.add(item.rule_id)
        _append_denial_hints(item, _repeat_denial_hints(ctx, item, repeat_count))

    if repeated_rule_ids:
        ctx.state.set_retry_lock(
            ctx.session_id,
            payload=RetryLockPayload(
                repeated_rule_ids=sorted(repeated_rule_ids),
                current_rule_ids=current_rule_ids,
                paths=_retry_lock_paths(ctx),
                attempt_fingerprint=attempt_fingerprint,
                count=max_repeat_count,
            ),
        )

    _clear_resolved_thin_wrapper_hits(ctx, denied)


def inject_recent_failure_context(
    ctx: HookContext, findings: list[RuleFinding]
) -> None:
    if ctx.event_name != "SessionStart":
        return
    repeated = ctx.state.recent_repeated_failures(ctx.session_id, limit=4)
    if not repeated:
        return
    lines = [
        "## Recent repeated failures",
        "Avoid repeating these patterns this session:",
    ]
    for item in repeated:
        rule_id = item.get("rule_id", "unknown")
        path = item.get(METADATA_PATH, "__pathless__")
        count = item.get("count", 0)
        if path == "__pathless__":
            lines.append(f"- {rule_id} x{count}")
        else:
            lines.append(f"- {rule_id} on {Path(str(path)).name} x{count}")
    findings.append(
        RuleFinding(
            rule_id="SESSION-RECENT-FAILURES",
            title="Session repeated-failure memory",
            severity=Severity.LOW,
            additional_context="\n".join(lines),
        )
    )


@dataclass(frozen=True, slots=True)
class _RetryBudgetBlock:
    lock: ObjectDict
    current_attempt_fingerprint: str | None
    repeated_rule_ids: set[str]
    current_rule_ids: set[str]
    matched_rule_ids: list[str]


def _retry_budget_block(
    ctx: HookContext, findings: list[RuleFinding]
) -> _RetryBudgetBlock | None:
    lock = ctx.state.get_retry_lock(ctx.session_id)
    if not lock:
        return None
    if ctx.state.has_repair_plan(ctx.session_id):
        ctx.state.clear_retry_lock(ctx.session_id)
        return None
    current_attempt_fingerprint = _attempt_fingerprint(ctx)
    locked_attempt_fingerprint = lock.get("attempt_fingerprint")
    if (
        isinstance(locked_attempt_fingerprint, str)
        and current_attempt_fingerprint != locked_attempt_fingerprint
    ):
        return None
    current_rule_ids = set(_current_denied_rule_ids(findings))
    if not current_rule_ids:
        return None
    repeated_rule_ids = {
        item
        for item in object_list(lock.get("repeated_rule_ids"))
        if isinstance(item, str)
    }
    matched_rule_ids = sorted(current_rule_ids & repeated_rule_ids)
    if repeated_rule_ids and not matched_rule_ids:
        return None
    return _RetryBudgetBlock(
        lock=lock,
        current_attempt_fingerprint=current_attempt_fingerprint,
        repeated_rule_ids=repeated_rule_ids,
        current_rule_ids=current_rule_ids,
        matched_rule_ids=matched_rule_ids,
    )


def _retry_budget_finding(block: _RetryBudgetBlock) -> RuleFinding:
    return RuleFinding(
        rule_id="RETRY-BUDGET-001",
        title="Retry budget enforcement",
        severity=Severity.HIGH,
        decision=DENY,
        message=(
            "Third write attempt blocked after repeated denies of the same edit pattern. "
            "Reread the file, name violated constraints, and write a short repair plan first."
        ),
        metadata={
            "repeated_rule_ids": sorted(block.repeated_rule_ids),
            "matched_rule_ids": block.matched_rule_ids,
            "current_rule_ids": sorted(block.current_rule_ids),
            "locked_rule_ids": block.lock.get("current_rule_ids"),
            "paths_locked": block.lock.get("paths"),
            "attempt_fingerprint_locked": block.lock.get("attempt_fingerprint"),
            "attempt_fingerprint_current": block.current_attempt_fingerprint,
            "retry_count": block.lock.get("count"),
        },
        additional_context=(
            "Required before next write:\n"
            "1) reread the target file\n"
            "2) list violated constraints\n"
            "3) write a short repair plan"
        ),
    )


def enforce_retry_budget(ctx: HookContext, findings: list[RuleFinding]) -> None:
    if ctx.event_name not in {PRE_TOOL_USE, PERMISSION_REQUEST}:
        return
    if not is_edit_like_tool(ctx.tool_name):
        return
    block = _retry_budget_block(ctx, findings)
    if block is not None:
        findings.append(_retry_budget_finding(block))


def capture_repair_plan_signal(ctx: HookContext) -> None:
    if ctx.event_name not in {"UserPromptSubmit", "SessionStart"}:
        return
    prompt = ctx.user_prompt.lower()
    if "repair plan" not in prompt:
        return
    constraints_named = "constraint" in prompt or "rule" in prompt
    reread_done = "reread" in prompt or "re-read" in prompt or "read" in prompt
    ctx.state.mark_repair_plan(ctx.session_id, constraints_named, reread_done)
