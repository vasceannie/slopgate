"""Projected pre-edit lint hook rule."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from typing_extensions import override

from slopgate.constants import (
    BLOCK,
    CONTEXT,
    DENY,
    METADATA_PATH,
    PERMISSION_REQUEST,
    PRE_TOOL_USE,
    WARN,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule

from .collectors import PROJECTED_COLLECTOR_SCOPES, collect_projected_lint_report
from .overlay import OverlayUnavailableError, projected_overlay
from .parity import (
    PROJECTED_RULE_ID,
    ProjectionParitySnapshot,
    record_parity_snapshot,
)
from .projection import ProjectedFiles, ProjectionSkip, build_projection

if TYPE_CHECKING:
    from slopgate.context import HookContext
    from slopgate.rules.common.quality.lint import TouchedLintReport

_ADVISORY_ACTIONS = frozenset({CONTEXT, WARN, "ask"})
_BLOCKING_ACTIONS = frozenset({BLOCK, DENY})


def _surface_action(ctx: HookContext) -> str | None:
    surface = ctx.config.rule_surfaces.get(PROJECTED_RULE_ID)
    return surface.hook.action if surface is not None else None


def _projection_digest(projection: ProjectedFiles) -> str:
    digest = hashlib.sha256()
    for item in projection.files:
        digest.update(item.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.content.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _skip_finding(skip: ProjectionSkip, action: str | None) -> RuleFinding:
    context_enabled = action in _ADVISORY_ACTIONS | _BLOCKING_ACTIONS
    context = (
        f"Projected pre-edit lint skipped: {skip.detail} "
        "QUALITY-LINT-001 remains authoritative after the edit."
        if context_enabled
        else None
    )
    metadata: dict[str, object] = {
        "rollout": "shadow" if action is None else action,
        "skip_reason": skip.reason,
        "paths": list(skip.paths),
        "authoritative_rule_id": "QUALITY-LINT-001",
        "surface_action_cap": "advisory",
    }
    if skip.paths:
        metadata[METADATA_PATH] = skip.paths[0]
    return RuleFinding(
        rule_id=PROJECTED_RULE_ID,
        title="Projected pre-edit lint",
        severity=Severity.MEDIUM,
        message=f"Projected lint skipped: {skip.reason}",
        additional_context=context,
        metadata=metadata,
    )


def _projected_message(report: TouchedLintReport) -> str:
    failures = ", ".join(report.failures)
    targets = ", ".join(report.targets)
    return (
        f"[{PROJECTED_RULE_ID}] Projected pre-edit lint found {failures} for {targets}. "
        "Repair the proposed content before writing it. "
        "QUALITY-LINT-001 will run after the edit and remains authoritative."
    )


def _failure_finding(
    report: TouchedLintReport, action: str | None, projection_digest: str
) -> RuleFinding:
    blocking = action in _BLOCKING_ACTIONS
    advisory = action in _ADVISORY_ACTIONS
    metadata: dict[str, object] = {
        "rollout": "shadow" if action is None else action,
        "failing_collectors": report.failures,
        "collector_details": report.details,
        "collector_ids": report.collector_ids,
        "collector_scopes": sorted(PROJECTED_COLLECTOR_SCOPES),
        "paths": report.targets,
        "projection_digest": projection_digest,
        "authoritative_rule_id": "QUALITY-LINT-001",
    }
    if report.first_diagnostic is not None:
        metadata["first_diagnostic"] = report.first_diagnostic
    if report.targets:
        metadata[METADATA_PATH] = report.targets[0]
    message = _projected_message(report)
    return RuleFinding(
        rule_id=PROJECTED_RULE_ID,
        title="Projected pre-edit lint",
        severity=Severity.HIGH if blocking else Severity.LOW,
        decision=DENY if blocking else None,
        message=message if blocking else None,
        additional_context=message if advisory else None,
        metadata=metadata,
    )


class _ProjectedPreEditLintRule(Rule):
    rule_id = PROJECTED_RULE_ID
    title = "Projected pre-edit lint"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST)

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not ctx.mutating:
            return []
        action = _surface_action(ctx)
        projection = build_projection(ctx)
        if isinstance(projection, ProjectionSkip):
            return [] if not projection.paths else [_skip_finding(projection, action)]
        projection_digest = _projection_digest(projection)
        try:
            with projected_overlay(ctx.config.repo_root, projection.files) as overlay:
                report = collect_projected_lint_report(overlay.root, overlay.files)
        except OverlayUnavailableError as exc:
            skip = ProjectionSkip(
                tuple(item.relative_path for item in projection.files),
                "overlay_unavailable",
                str(exc),
            )
            return [_skip_finding(skip, action)]
        if action not in _BLOCKING_ACTIONS:
            record_parity_snapshot(
                ctx.config.trace_dir,
                ProjectionParitySnapshot(
                    session_id=ctx.session_id,
                    paths=report.targets,
                    collector_ids=report.collector_ids,
                    projection_digest=projection_digest,
                ),
            )
        if not report.failures:
            return []
        return [_failure_finding(report, action, projection_digest)]


ProjectedPreEditLintRule = _ProjectedPreEditLintRule


__all__ = ["ProjectedPreEditLintRule"]
