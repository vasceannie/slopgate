from __future__ import annotations

from slopgate.constants import DENY, METADATA_PATH
from slopgate.context import HookContext
from slopgate.models import RuleFinding

from .constants import RULE_HINTS
from .paths import _is_test_path, failure_class, finding_path
from .quality import _quality_lint_hint


def long_params_hint(item: RuleFinding) -> str:
    path = finding_path(item)
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


def rule_hint(ctx: HookContext, item: RuleFinding) -> str | None:
    if item.rule_id == "QUALITY-LINT-001":
        return _quality_lint_hint(ctx, item)
    if item.rule_id == "PY-CODE-009":
        return long_params_hint(item)
    return RULE_HINTS.get(item.rule_id)


def denial_context(ctx: HookContext, item: RuleFinding, repeat_count: int) -> str:
    parts = [
        f"Hook phase: {ctx.event_name}",
        f"tool: {ctx.tool_name or 'unknown'}",
        f"failure class: {failure_class(item.rule_id)}",
    ]
    path = finding_path(item)
    if path:
        parts.append(f"target: {path}")
        if item.metadata.get(METADATA_PATH) == "content":
            parts.append(f"patch content touched: {path}")
    if repeat_count >= 2:
        parts.append(f"repeat count: {repeat_count}")
    return "; ".join(parts) + "."


def denial_findings(findings: list[RuleFinding]) -> list[RuleFinding]:
    return [item for item in findings if item.decision in {DENY, "block"}]


def retry_budget_relevant_denials(findings: list[RuleFinding]) -> list[RuleFinding]:
    return [
        item for item in denial_findings(findings) if item.rule_id != "RETRY-BUDGET-001"
    ]
