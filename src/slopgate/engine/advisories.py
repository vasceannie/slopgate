from __future__ import annotations

from slopgate.constants import METADATA_PATH
from slopgate.context import HookContext
from slopgate.models import RuleFinding

from ._retry import _normalize_attempt_path

COMPACT_CONTEXT_RULE_IDS = frozenset({"PY-CODE-012"})
SAME_PATH_SUPPRESSION_REASON = "same_path_lower_ratio"
REPEAT_SUPPRESSION_REASON = "repeat_context_advisory"


def _metadata_path(finding: RuleFinding) -> str | None:
    value = finding.metadata.get(METADATA_PATH)
    return value if isinstance(value, str) and value else None


def _numeric_metadata(finding: RuleFinding, key: str) -> int:
    value = finding.metadata.get(key)
    return value if isinstance(value, int) else 0


def _access_ratio(finding: RuleFinding) -> tuple[float, int]:
    accesses = _numeric_metadata(finding, "accesses")
    total = _numeric_metadata(finding, "total")
    ratio = accesses / total if total > 0 else 0.0
    return (ratio, accesses)


def _suppress_context(finding: RuleFinding, *, repeat_count: int, reason: str) -> None:
    finding.message = None
    finding.additional_context = None
    finding.metadata["context_suppressed"] = True
    finding.metadata["context_suppression_reason"] = reason
    finding.metadata["repeat_count"] = repeat_count


def _record_path_group(
    ctx: HookContext, path_key: str, items: list[RuleFinding]
) -> None:
    visible = max(items, key=_access_ratio)
    repeat_count = ctx.state.record_advisory_hit(
        ctx.session_id, visible.rule_id, path_key
    )
    for item in items:
        item.metadata["normalized_path"] = path_key
        item.metadata["repeat_count"] = repeat_count
        if repeat_count > 1:
            _suppress_context(
                item, repeat_count=repeat_count, reason=REPEAT_SUPPRESSION_REASON
            )
        elif item is not visible:
            _suppress_context(
                item, repeat_count=repeat_count, reason=SAME_PATH_SUPPRESSION_REASON
            )


def compact_context_advisories(ctx: HookContext, findings: list[RuleFinding]) -> None:
    """Suppress repeat advisory prose while preserving finding metadata."""
    grouped: dict[str, list[RuleFinding]] = {}
    for finding in findings:
        if finding.rule_id not in COMPACT_CONTEXT_RULE_IDS:
            continue
        path_value = _metadata_path(finding)
        if path_value is None:
            continue
        grouped.setdefault(_normalize_attempt_path(ctx, path_value), []).append(finding)

    for path_key, items in grouped.items():
        _record_path_group(ctx, path_key, items)
