from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from collections.abc import Mapping
from pathlib import Path
from time import monotonic

from vibeforcer._types import ObjectDict, object_list
from vibeforcer.adapters import get_adapter
from vibeforcer.adapters.base import PlatformAdapter
from typing import Literal

from vibeforcer.config import (
    is_path_skipped,
    is_repo_disabled,
    is_repo_enrolled,
    resolve_repo_root,
)
from vibeforcer.context import HookContext, build_context
from vibeforcer.enrichment import enrich_findings
from vibeforcer.models import EngineResult, RuleFinding, Severity
from vibeforcer.rules import build_always_on_rules, build_repo_strict_rules
from vibeforcer.rules.base import Rule
from vibeforcer.util import warning
from vibeforcer.util.payloads import is_edit_like_tool


DECISION_ORDER: dict[str | None, int] = {
    "deny": 4,
    "block": 4,
    "ask": 3,
    "allow": 2,
    None: 0,
}


def _finding_sort_key(item: RuleFinding) -> tuple[int, int]:
    return (DECISION_ORDER.get(item.decision, 0), int(item.severity))


def _merge_updated_input(findings: list[RuleFinding]) -> dict[str, object]:
    merged: dict[str, object] = {}
    for finding in findings:
        merged.update(finding.updated_input)
    return merged


def _collect_context(findings: list[RuleFinding]) -> str | None:
    parts = [item.additional_context for item in findings if item.additional_context]
    if not parts:
        return None
    return "\n\n".join(dict.fromkeys(parts))


def _top_decision(findings: list[RuleFinding]) -> str | None:
    if not findings:
        return None
    return max(findings, key=_finding_sort_key).decision


def _apply_severity_overrides(
    findings: list[RuleFinding],
    overrides: dict[str, str],
) -> None:
    """Mutate findings in-place to apply per-repo severity overrides."""
    for finding in findings:
        if finding.rule_id not in overrides:
            continue
        override = overrides[finding.rule_id]
        if override.lower() == "warn":
            finding.severity = Severity.LOW
            finding.decision = None
        else:
            finding.severity = Severity.from_value(override)


def _serialize_findings(findings: list[RuleFinding]) -> list[dict[str, object]]:
    return [
        {
            "rule_id": item.rule_id,
            "severity": item.severity.as_name(),
            "decision": item.decision,
            "message": item.message,
            "additional_context": item.additional_context,
            "metadata": item.metadata,
        }
        for item in findings
    ]


def _trace_identity(ctx: HookContext, platform: str) -> dict[str, object]:
    return {
        "platform": platform,
        "event_name": ctx.event_name,
        "session_id": ctx.session_id,
        "tool_name": ctx.tool_name,
    }


def _platform_capability(platform: str) -> tuple[str, str | None]:
    normalized = platform.strip().lower()
    if normalized == "opencode":
        return (
            "degraded",
            "opencode uses plugin events rather than Claude-style hooks; prompt interception is unavailable, stop blocking is advisory, and post-tool deny is best-effort",
        )
    if normalized == "codex":
        return (
            "partial",
            "codex hooks are experimental and currently provide Bash-focused tool interception rather than Claude-style tool parity",
        )
    return ("full", None)


def _error_trace_payload(
    identity: dict[str, object],
    rule_id: str,
    exc: Exception,
    elapsed_ms: float,
) -> dict[str, object]:
    """Build the trace payload dict for a rule evaluation error."""
    payload = dict(identity)
    payload.update(
        {
            "rule_id": rule_id,
            "elapsed_ms": elapsed_ms,
            "error": repr(exc),
        }
    )
    return payload


@dataclass(slots=True)
class _EvalAccumulator:
    """Groups mutable state passed through the evaluation pipeline."""

    findings: list[RuleFinding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _trace_findings(
    ctx: HookContext,
    platform: str,
    items: list[RuleFinding],
    elapsed_ms: float,
) -> None:
    identity = _trace_identity(ctx, platform)
    for item in items:
        payload = dict(identity)
        payload.update(
            {
                "rule_id": item.rule_id,
                "elapsed_ms": elapsed_ms,
                "severity": item.severity.as_name(),
                "decision": item.decision,
                "message": item.message,
                "additional_context": item.additional_context,
                "metadata": item.metadata,
            }
        )
        ctx.trace.rule(payload)


def _run_rule(
    rule: Rule,
    ctx: HookContext,
    platform: str,
    acc: _EvalAccumulator,
) -> None:
    """Evaluate a single rule, collecting findings and errors."""
    identity = _trace_identity(ctx, platform)
    start = monotonic()
    try:
        result = rule.evaluate(ctx)
        elapsed_ms = round((monotonic() - start) * 1000.0, 3)
        if not result:
            return
        _apply_severity_overrides(result, ctx.config.severity_overrides)
        acc.findings.extend(result)
        _trace_findings(ctx, platform, result, elapsed_ms)
    except Exception as exc:
        elapsed_ms = round((monotonic() - start) * 1000.0, 3)
        acc.errors.append(f"{rule.rule_id}: {exc}")
        warning(
            "rule evaluation failed",
            rule_id=rule.rule_id,
            event_name=ctx.event_name,
            tool_name=ctx.tool_name,
            error=str(exc),
        )
        ctx.trace.rule(_error_trace_payload(identity, rule.rule_id, exc, elapsed_ms))


def _safe_enrich(
    ctx: HookContext,
    platform: str,
    acc: _EvalAccumulator,
) -> None:
    """Run enrichment with error capture instead of silent swallow."""
    identity = _trace_identity(ctx, platform)
    findings_before = len(acc.findings)
    start = monotonic()
    try:
        enrich_findings(acc.findings, ctx)
        elapsed_ms = round((monotonic() - start) * 1000.0, 3)
        findings_after = len(acc.findings)
        payload = dict(identity)
        payload.update(
            {
                "rule_id": "ENRICHMENT",
                "elapsed_ms": elapsed_ms,
                "metadata": {
                    "findings_before": findings_before,
                    "findings_after": findings_after,
                    "findings_delta": findings_after - findings_before,
                },
            }
        )
        ctx.trace.rule(payload)
    except Exception as exc:
        elapsed_ms = round((monotonic() - start) * 1000.0, 3)
        acc.errors.append(f"enrichment: {exc}")
        warning(
            "enrichment failed",
            event_name=ctx.event_name,
            tool_name=ctx.tool_name,
            error=str(exc),
        )
        ctx.trace.rule(_error_trace_payload(identity, "ENRICHMENT", exc, elapsed_ms))


EnforcementMode = Literal["outside_repo", "repo_strict", "repo_relaxed"]


def _resolve_enforcement_mode(ctx: HookContext) -> EnforcementMode:
    repo_cwd = Path(ctx.cwd) if ctx.cwd else Path.cwd()
    repo_root = resolve_repo_root(repo_cwd) or repo_cwd.resolve()

    if not is_repo_enrolled(repo_root):
        return "outside_repo"

    if is_repo_disabled(repo_root):
        return "repo_relaxed"

    return "repo_strict"


def _run_rules(ctx: HookContext, platform: str, mode: EnforcementMode) -> _EvalAccumulator:
    """Build and evaluate applicable rules for the selected enforcement mode."""
    acc = _EvalAccumulator()
    disabled = set(ctx.config.disabled_rules)

    rules: list[Rule] = [*build_always_on_rules(ctx)]
    repo_root = resolve_repo_root(Path(ctx.cwd) if ctx.cwd else Path.cwd())
    effective_root = repo_root or (Path(ctx.cwd) if ctx.cwd else Path.cwd())

    if mode == "repo_strict" and not is_path_skipped(effective_root, ctx.config.skip_paths):
        rules.extend(build_repo_strict_rules(ctx))

    for rule in rules:
        if rule.supports(ctx.event_name) and rule.rule_id not in disabled:
            _run_rule(rule, ctx, platform, acc)
    _safe_enrich(ctx, platform, acc)
    return acc


_REPLAN_PROMPT = (
    "If a hook denies or blocks your change, do not immediately retry the same edit pattern. "
    "Classify the failure first: structural, policy/tooling, or quality. Change approach before retrying. "
    "If the same file or rule is denied twice, stop and make a short repair plan before the next write. "
    "Prefer small helper extractions, params objects, and named constants over large rewrites."
)

_RULE_HINTS: dict[str, str] = {
    "PY-AST-001": (
        "Next step: stop refactoring; restore parseability with a full reread "
        "plus `python3 -m py_compile <file>`."
    ),
    "PY-CODE-008": "Next step: extract one helper first; avoid full-file rewrites.",
    "PY-CODE-010": (
        "Next step: break the expression or extract an intermediate variable; "
        "do not hide long lines with comments."
    ),
    "PY-CODE-011": (
        "Next step: use guard clauses or extract the inner branch before "
        "adding more conditionals."
    ),
    "PY-CODE-013": (
        "Next step: inline trivial pass-throughs unless the wrapper owns a real "
        "domain boundary. A real wrapper does at least one job: validates/normalizes "
        "inputs, changes abstraction level with a domain name, centralizes policy, "
        "caching, permission, or logging, adapts one interface to another, or hides "
        "unstable third-party API details. If it is a real boundary, make the "
        "behavior explicit in the body/name; otherwise replace calls with the target "
        "and delete the wrapper."
    ),
    "PY-CODE-014": (
        "Next step: split the class by responsibility into composed "
        "collaborators, not random method moves."
    ),
    "PY-CODE-015": (
        "Next step: replace branch chains with named predicates or dispatch "
        "before adding behavior."
    ),
    "PY-CODE-017": (
        "Recovery skill: load `code-hygiene-refactor` before retrying. Read the "
        "quality/architecture and python/project-structure rule shards. Convert "
        "flat `prefix_*.py` siblings into a `prefix/` package with a small "
        "`__init__.py` facade/re-export layer; do not add another flat sibling."
    ),
    "PY-CODE-018": (
        "Recovery skill: load `code-hygiene-refactor` before retrying; if the "
        "repair spans many files, switch to `hygiene-orchestrator`. Next step: "
        "choose a split shape first: conftest registry/support modules, "
        "module-to-package facade, thin __init__.py, CLI/router-to-services, "
        "test-module split, or data/resources extraction."
    ),
    "PY-TEST-003": (
        "Next step: convert loops-with-asserts into pytest parametrization "
        "with readable ids."
    ),
    "PY-TEST-004": "Next step: move shared fixtures into the narrowest useful conftest.py.",
    "PY-TYPE-002": (
        "Next step: remove the suppression and add a Protocol, TypedDict, "
        "overload, or local stub."
    ),
    "PY-QUALITY-005": (
        "Next step: catch the specific expected empty case; propagate "
        "corruption/infrastructure failures."
    ),
    "PY-QUALITY-010": (
        "Next step: define UPPER_CASE constants first, then replace "
        "repeated literals."
    ),
    "GLOBAL-BUILTIN-SYSTEM-PROTECTION": (
        "Next step: do not touch protected system paths as file targets. "
        "Executable-position paths like `/usr/bin/rg` are allowed; if this "
        "was /dev/null suppression, handle stderr explicitly instead."
    ),
    "GLOBAL-BUILTIN-HOOK-INFRA-EXEC": (
        "Next step: treat hook infrastructure as read-only unless Trav "
        "explicitly approved this edit."
    ),
    "QA-PATH-003": (
        "Next step: do not edit quality tests. Fix the source rule implementation "
        "under `src/vibeforcer/...`; if expected output legitimately changed, "
        "update only `tests/quality/baselines.json`, then run "
        "`python -m pytest -q tests/quality`."
    ),
    "SHELL-001": (
        "Do not run shell retries. Next step: use structured read/edit/write "
        "tools or handle failures explicitly."
    ),
    "PY-SHELL-001": "Do not run shell retries. Next step: use structured tools.",
}


def _is_test_path(path_value: str | None) -> bool:
    if path_value is None:
        return False
    normalized = path_value.replace("\\", "/")
    return normalized.startswith("tests/") or "/tests/" in normalized


def _quality_lint_hint(ctx: HookContext, item: RuleFinding) -> str:
    phase_note = ""
    if ctx.event_name == "PostToolUse":
        phase_note = "PostToolUse already-mutated repair protocol: "
    path = _finding_path(item)
    pathless_note = ""
    if path is None:
        pathless_note = (
            " Path was not extracted from the tool payload. Use the file you just "
            "wrote/edited; do not blindly rerun the same patch."
        )
    hint = (
        f"{phase_note}The edit landed, but touched-file lint found quality debt. "
        "Do not continue feature work. Next action: 1) reread the touched file, "
        "2) fix only the reported collector/hit, 3) verify from the project root "
        "with the smallest repo-root quality command: `vibeforcer lint check` "
        "(no file/path argument), "
        "4) if no path is available, inspect the last edited file from tool context."
        f"{pathless_note}"
    )
    if _quality_lint_has_oversized_module(item):
        hint = (
            f"{hint} Recovery skill: load `code-hygiene-refactor` before retrying; "
            "if the repair spans many files, switch to `hygiene-orchestrator`. "
            "Use the oversized-module split playbook instead of patching around "
            "line-count symptoms."
        )
    return hint


def _quality_lint_has_oversized_module(item: RuleFinding) -> bool:
    collectors = object_list(item.metadata.get("failing_collectors"))
    return any(
        isinstance(collector, str)
        and collector.startswith(("oversized-module:", "oversized-module-soft:"))
        for collector in collectors
    )


def _long_params_hint(item: RuleFinding) -> str:
    path = _finding_path(item)
    if _is_test_path(path):
        return (
            "Next step: this test helper is pretending to be a constructor. Prefer "
            "a named Case dataclass or builder defaults so each test only overrides "
            "the meaningful fields. Forwarding every arg to another constructor is "
            "still too many params."
        )
    return (
        "Next step: group by semantic meaning, not arbitrary parameter bags. "
        "Introduce a typed params object, dataclass, or TypedDict only when the "
        "fields travel together as one concept."
    )


def _rule_hint(ctx: HookContext, item: RuleFinding) -> str | None:
    if item.rule_id == "QUALITY-LINT-001":
        return _quality_lint_hint(ctx, item)
    if item.rule_id == "PY-CODE-009":
        return _long_params_hint(item)
    return _RULE_HINTS.get(item.rule_id)


def _failure_class(rule_id: str) -> str:
    if rule_id.startswith("PY-CODE") or rule_id.startswith("PY-QUALITY"):
        return "structural" if rule_id.startswith("PY-CODE") else "quality"
    if "SHELL" in rule_id or rule_id.startswith("GIT-"):
        return "policy_tooling"
    return "quality"


def _finding_path(item: RuleFinding) -> str | None:
    path = item.metadata.get("path")
    if isinstance(path, str) and path:
        return path
    return None


def _denial_context(ctx: HookContext, item: RuleFinding, repeat_count: int) -> str:
    parts = [
        f"Hook phase: {ctx.event_name}",
        f"tool: {ctx.tool_name or 'unknown'}",
        f"failure class: {_failure_class(item.rule_id)}",
    ]
    path = _finding_path(item)
    if path:
        parts.append(f"target: {path}")
    if repeat_count >= 2:
        parts.append(f"repeat count: {repeat_count}")
    return "; ".join(parts) + "."


def _denial_findings(findings: list[RuleFinding]) -> list[RuleFinding]:
    return [item for item in findings if item.decision in {"deny", "block"}]


def _retry_budget_relevant_denials(findings: list[RuleFinding]) -> list[RuleFinding]:
    return [item for item in _denial_findings(findings) if item.rule_id != "RETRY-BUDGET-001"]


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
    return sorted({item.rule_id for item in _retry_budget_relevant_denials(findings)})


def _dedupe_findings(findings: list[RuleFinding]) -> list[RuleFinding]:
    unique: list[RuleFinding] = []
    seen: set[tuple[str, str | None, str | None, str | None]] = set()
    for item in findings:
        key = (item.rule_id, item.decision, item.message, item.additional_context)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _filter_search_reminder_dedupe(ctx: HookContext, findings: list[RuleFinding]) -> list[RuleFinding]:
    reminder_indexes = [idx for idx, item in enumerate(findings) if item.rule_id == "REMIND-SEARCH-001"]
    if not reminder_indexes:
        return findings
    if ctx.state.should_emit_search_reminder(ctx.session_id):
        ctx.state.record_search_reminder(ctx.session_id)
        first = reminder_indexes[0]
        return [item for idx, item in enumerate(findings) if item.rule_id != "REMIND-SEARCH-001" or idx == first]
    return [item for item in findings if item.rule_id != "REMIND-SEARCH-001"]


def _apply_loop_aware_steering(ctx: HookContext, findings: list[RuleFinding]) -> None:
    denied = _retry_budget_relevant_denials(findings)
    attempt_fingerprint = _attempt_fingerprint(ctx)
    current_rule_ids = _current_denied_rule_ids(findings)
    repeated_rule_ids: set[str] = set()
    max_repeat_count = 0
    for item in denied:
        path_value = _finding_path(item)
        state_path = _normalize_attempt_path(ctx, path_value) if path_value else None
        repeat_count = ctx.state.record_deny_hit(
            ctx.session_id,
            item.rule_id,
            state_path,
            attempt_fingerprint,
        )
        classification = _failure_class(item.rule_id)
        item.metadata["failure_class"] = classification
        item.metadata["repeat_count"] = repeat_count
        if attempt_fingerprint:
            item.metadata["attempt_fingerprint"] = attempt_fingerprint
        max_repeat_count = max(max_repeat_count, repeat_count)
        if repeat_count >= 2:
            repeated_rule_ids.add(item.rule_id)
            item.metadata["repeat_hit"] = True
            item.message = ((item.message or "").rstrip() + " Change design before retrying.").strip()
        if repeat_count >= 3 and item.decision != "block":
            item.decision = "block"
            item.severity = max(item.severity, Severity.HIGH)
            item.metadata["escalated"] = True
        hints = [_denial_context(ctx, item, repeat_count), _REPLAN_PROMPT]
        rule_hint = _rule_hint(ctx, item)
        if rule_hint:
            hints.append(rule_hint)
        if repeat_count >= 2:
            hints.append("Repeated deny detected: write a short repair plan before your next write.")
        item.additional_context = "\n\n".join(
            part for part in [item.additional_context, *hints] if part
        )

    if repeated_rule_ids:
        retry_paths = sorted(
            {
                _normalize_attempt_path(ctx, path_value)
                for path_value in ctx.candidate_paths
                if path_value
            }
        )
        ctx.state.set_retry_lock(
            ctx.session_id,
            repeated_rule_ids=sorted(repeated_rule_ids),
            current_rule_ids=current_rule_ids,
            paths=retry_paths,
            attempt_fingerprint=attempt_fingerprint,
            count=max_repeat_count,
        )

    touched_paths = [target.path for target in ctx.content_targets if target.path]
    if touched_paths:
        found_pairs = {
            (
                item.rule_id,
                _normalize_attempt_path(ctx, path_value)
                if (path_value := _finding_path(item)) is not None
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


def _inject_recent_failure_context(ctx: HookContext, findings: list[RuleFinding]) -> None:
    if ctx.event_name != "SessionStart":
        return
    repeated = ctx.state.recent_repeated_failures(ctx.session_id, limit=4)
    if not repeated:
        return
    lines = ["## Recent repeated failures", "Avoid repeating these patterns this session:"]
    for item in repeated:
        rule_id = item.get("rule_id", "unknown")
        path = item.get("path", "__pathless__")
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


def _enforce_retry_budget(ctx: HookContext, findings: list[RuleFinding]) -> None:
    if ctx.event_name not in {"PreToolUse", "PermissionRequest"}:
        return
    if not is_edit_like_tool(ctx.tool_name):
        return
    lock = ctx.state.get_retry_lock(ctx.session_id)
    if not lock:
        return
    if ctx.state.has_repair_plan(ctx.session_id):
        ctx.state.clear_retry_lock(ctx.session_id)
        return
    current_attempt_fingerprint = _attempt_fingerprint(ctx)
    locked_attempt_fingerprint = lock.get("attempt_fingerprint")
    if (
        isinstance(locked_attempt_fingerprint, str)
        and current_attempt_fingerprint != locked_attempt_fingerprint
    ):
        return
    current_rule_ids = set(_current_denied_rule_ids(findings))
    if not current_rule_ids:
        return
    repeated_rule_ids = {
        item
        for item in object_list(lock.get("repeated_rule_ids"))
        if isinstance(item, str)
    }
    matched_rule_ids = sorted(current_rule_ids & repeated_rule_ids)
    if repeated_rule_ids and not matched_rule_ids:
        return
    findings.append(
        RuleFinding(
            rule_id="RETRY-BUDGET-001",
            title="Retry budget enforcement",
            severity=Severity.HIGH,
            decision="deny",
            message=(
                "Third write attempt blocked after repeated denies of the same edit pattern. "
                "Reread the file, name violated constraints, and write a short repair plan first."
            ),
            metadata={
                "repeated_rule_ids": sorted(repeated_rule_ids),
                "matched_rule_ids": matched_rule_ids,
                "current_rule_ids": sorted(current_rule_ids),
                "locked_rule_ids": lock.get("current_rule_ids"),
                "paths_locked": lock.get("paths"),
                "attempt_fingerprint_locked": locked_attempt_fingerprint,
                "attempt_fingerprint_current": current_attempt_fingerprint,
                "retry_count": lock.get("count"),
            },
            additional_context=(
                "Required before next write:\n"
                "1) reread the target file\n"
                "2) list violated constraints\n"
                "3) write a short repair plan"
            ),
        )
    )


def _capture_repair_plan_signal(ctx: HookContext) -> None:
    if ctx.event_name not in {"UserPromptSubmit", "SessionStart"}:
        return
    prompt = ctx.user_prompt.lower()
    if "repair plan" not in prompt:
        return
    constraints_named = "constraint" in prompt or "rule" in prompt
    reread_done = "reread" in prompt or "re-read" in prompt or "read" in prompt
    ctx.state.mark_repair_plan(ctx.session_id, constraints_named, reread_done)


def render_output(
    ctx: HookContext,
    findings: list[RuleFinding],
    adapter: PlatformAdapter | None = None,
) -> ObjectDict | None:
    if not findings:
        return None

    adapter = adapter or get_adapter("claude")
    return adapter.render_output(
        ctx.event_name,
        findings,
        context=_collect_context(findings),
        updated_input=_merge_updated_input(findings),
        decision=_top_decision(findings),
    )


def evaluate_payload(
    payload_dict: Mapping[str, object],
    platform: str = "claude",
) -> EngineResult:
    adapter = get_adapter(platform)
    ctx = build_context(adapter.normalize_payload(payload_dict))

    enforcement_mode = _resolve_enforcement_mode(ctx)
    resolved_repo_root = resolve_repo_root(Path(ctx.cwd) if ctx.cwd else Path.cwd())
    capability, degraded_reason = _platform_capability(platform)

    ctx.trace.event(
        {
            "platform": platform,
            "platform_capability": capability,
            "degraded_reason": degraded_reason,
            "event_name": ctx.event_name,
            "session_id": ctx.session_id,
            "tool_name": ctx.tool_name,
            "candidate_paths": ctx.candidate_paths,
            "languages": sorted(ctx.languages),
            "enforcement_mode": enforcement_mode,
            "resolved_repo_root": str(resolved_repo_root) if resolved_repo_root else None,
        }
    )

    _capture_repair_plan_signal(ctx)
    acc = _run_rules(ctx, platform, enforcement_mode)
    _enforce_retry_budget(ctx, acc.findings)
    _apply_loop_aware_steering(ctx, acc.findings)
    _inject_recent_failure_context(ctx, acc.findings)
    acc.findings = _filter_search_reminder_dedupe(ctx, acc.findings)
    acc.findings = _dedupe_findings(acc.findings)
    output = render_output(ctx, acc.findings, adapter=adapter)

    ctx.trace.result(
        {
            "platform": platform,
            "platform_capability": capability,
            "degraded_reason": degraded_reason,
            "event_name": ctx.event_name,
            "session_id": ctx.session_id,
            "tool_name": ctx.tool_name,
            "findings": _serialize_findings(acc.findings),
            "errors": acc.errors,
            "output": output,
            "enforcement_mode": enforcement_mode,
            "resolved_repo_root": str(resolved_repo_root) if resolved_repo_root else None,
        }
    )
    return EngineResult(
        event_name=ctx.event_name,
        findings=acc.findings,
        output=output,
        errors=acc.errors,
    )
