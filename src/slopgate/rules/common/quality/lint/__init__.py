"""Authoritative post-edit touched-file lint rule."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from slopgate.constants import BLOCK, METADATA_PATH, POST_TOOL_USE, PRE_TOOL_USE
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled
from slopgate.rules.projected_lint.parity import pop_parity_snapshot
from slopgate.util.payloads import is_mutating_tool_use

from ..._shell_safe_read import command_has_word
from .reporting import (
    TouchedLintReport,
    collect_lint_report_for_files,
    collect_touched_lint_report,
    collect_touched_lint_failures,
    lint_message,
    python_lint_targets,
    resolve_python_candidates,
    violation_details,
)

if TYPE_CHECKING:
    from slopgate.context import HookContext


class SearchReminderRule(Rule):
    rule_id: str = "REMIND-SEARCH-001"
    title: str = "Search reminder"
    events: tuple[str, ...] = (PRE_TOOL_USE,)

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not ctx.config.search_reminder_message:
            return []
        if ctx.tool_name in {"Grep", "WebSearch", "Read"}:
            return []
        if ctx.shell_command and command_has_word(ctx.shell_command.lower(), "grep"):
            return [
                RuleFinding(
                    rule_id=self.rule_id,
                    title=self.title,
                    severity=Severity.LOW,
                    additional_context=ctx.config.search_reminder_message,
                )
            ]
        return []


class PostEditLintRule(Rule):
    rule_id: str = "QUALITY-LINT-001"
    title: str = "Touched-file lint advisory"
    events: tuple[str, ...] = (POST_TOOL_USE,)

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        if not is_mutating_tool_use(ctx):
            return []
        report = collect_touched_lint_report(ctx)
        if not report.failures:
            return []
        targets = report.targets or python_lint_targets(ctx)
        message = lint_message(
            report.failures, report.details, targets, report.first_diagnostic
        )
        metadata: dict[str, object] = {
            "failing_collectors": report.failures,
            "collector_details": report.details,
            "paths": targets,
        }
        parity = pop_parity_snapshot(
            ctx.config.trace_dir, ctx.session_id, targets, report.collector_ids
        )
        if parity is not None:
            metadata["projected_lint_parity"] = parity
        if report.first_diagnostic is not None:
            metadata["first_diagnostic"] = report.first_diagnostic
        if targets:
            metadata[METADATA_PATH] = targets[0]
        blocking = ctx.config.post_edit_quality_block_on_failure
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.HIGH if blocking else Severity.LOW,
                decision=BLOCK if blocking else None,
                message=message if blocking else None,
                additional_context=None if blocking else message,
                metadata=metadata,
            )
        ]


__all__ = [
    "PostEditLintRule",
    "SearchReminderRule",
    "TouchedLintReport",
    "collect_lint_report_for_files",
    "collect_touched_lint_report",
    "collect_touched_lint_failures",
    "lint_message",
    "python_lint_targets",
    "resolve_python_candidates",
    "violation_details",
]
