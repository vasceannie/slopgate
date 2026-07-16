"""Semantic repeat tracking and changed-design steering."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from slopgate.config import resolve_repo_root
from slopgate.constants import METADATA_PATH, METADATA_RULE_ID, SESSION_START
from slopgate.context import HookContext
from slopgate.models import RuleFinding, Severity
from slopgate.state import SemanticClearRequest, SemanticRetryLockPayload

from .._hints import (
    REPLAN_PROMPT,
    denial_context,
    failure_class,
    retry_budget_relevant_denials,
    rule_hint,
)
from .._hints.import_aliases import compress_repeated_import_alias_examples
from .guidance import recovery_guidance
from .identity import (
    attempt_fingerprint,
    normalize_attempt_path,
    operation_category,
    semantic_enforcement_key,
)


@dataclass(frozen=True, slots=True)
class _RecordedDenial:
    raw_key: str
    semantic_count: int


def _record_denial(
    ctx: HookContext, item: RuleFinding, fingerprint: str | None
) -> _RecordedDenial:
    key = semantic_enforcement_key(ctx, item)
    semantic_count, exact_count = ctx.state.record_semantic_deny(key, fingerprint)
    raw_key = ctx.state.semantic_state_key(key)
    item.metadata["repeat_count"] = semantic_count
    item.metadata["failure_class"] = failure_class(item.rule_id)
    item.metadata["semantic_repeat_count"] = semantic_count
    item.metadata["exact_repeat_count"] = exact_count
    item.metadata["semantic_key"] = hashlib.sha256(raw_key.encode()).hexdigest()
    item.metadata["semantic_rule_id"] = key.rule_id
    item.metadata["semantic_path"] = key.path
    item.metadata["semantic_operation_category"] = key.operation_category
    if fingerprint is not None:
        item.metadata["attempt_fingerprint"] = fingerprint
    return _RecordedDenial(raw_key, semantic_count)


def _append_context(ctx: HookContext, item: RuleFinding, count: int) -> None:
    parts = [item.additional_context, denial_context(ctx, item, count)]
    hint = rule_hint(ctx, item)
    if hint:
        parts.append(hint)
    if count >= 2:
        guidance = recovery_guidance(item.rule_id)
        item.metadata["repeat_hit"] = True
        item.metadata["recovery_guidance_id"] = guidance.guidance_id
        item.metadata["recovery_guidance_conflicts"] = list(guidance.conflicts)
        parts.append("Repeated deny detected: a materially changed design is required.")
        parts.append(REPLAN_PROMPT)
        parts.append(guidance.text)
    item.additional_context = "\n\n".join(part for part in parts if part)


def apply_loop_aware_steering(ctx: HookContext, findings: list[RuleFinding]) -> None:
    denied = retry_budget_relevant_denials(findings)
    fingerprint = attempt_fingerprint(ctx)
    active_keys: set[str] = set()
    for item in denied:
        compress_repeated_import_alias_examples(ctx, item)
        recorded = _record_denial(ctx, item, fingerprint)
        active_keys.add(recorded.raw_key)
        _append_context(ctx, item, recorded.semantic_count)
        if recorded.semantic_count >= 2:
            ctx.state.set_semantic_retry_lock(
                SemanticRetryLockPayload(
                    key=semantic_enforcement_key(ctx, item),
                    attempt_fingerprint=fingerprint,
                    count=recorded.semantic_count,
                )
            )

    if ctx.mutating:
        repo_root = (resolve_repo_root(ctx.cwd) or ctx.cwd).resolve(strict=False)
        touched_paths = frozenset(
            normalize_attempt_path(ctx, path) for path in ctx.candidate_paths if path
        )
        ctx.state.clear_resolved_semantic_denials(
            SemanticClearRequest(
                session_id=ctx.session_id,
                repo_root=str(repo_root),
                touched_paths=touched_paths,
                operation_category=operation_category(ctx),
                active_keys=frozenset(active_keys),
            )
        )


def inject_recent_failure_context(
    ctx: HookContext, findings: list[RuleFinding]
) -> None:
    if ctx.event_name != SESSION_START:
        return
    repeated = ctx.state.recent_semantic_failures(ctx.session_id, limit=4)
    if not repeated:
        return
    lines = ["## Recent repeated failures"]
    for item in repeated:
        rule_id = item.get(METADATA_RULE_ID, "unknown")
        path = item.get(METADATA_PATH, "__pathless__")
        count = item.get("count", 0)
        label = (
            rule_id
            if path == "__pathless__"
            else f"{rule_id} on {Path(str(path)).name}"
        )
        lines.append(f"- {label} x{count}")
    findings.append(
        RuleFinding(
            rule_id="SESSION-RECENT-FAILURES",
            title="Session repeated-failure memory",
            severity=Severity.LOW,
            additional_context="\n".join(lines),
        )
    )
