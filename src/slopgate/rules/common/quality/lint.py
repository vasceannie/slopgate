"""Post-edit touched-file lint backstop."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from typing_extensions import override

from slopgate.constants import (
    BLOCK,
    METADATA_PATH,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    PYTEST_TEST_PREFIX,
    QUALITY_FAILURE_PREVIEW_LIMIT,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled
from slopgate.util.path_filters import is_third_party_or_virtualenv_path
from slopgate.util.payloads import is_mutating_tool_use, lower_path

from .._shell_safe_read import command_has_word
from .guidance import (
    has_oversized_module_failure,
    lint_check_instruction,
    lint_target_summary,
    post_lint_oversized_guidance,
    preview_with_overflow,
)

if TYPE_CHECKING:
    from slopgate.context import HookContext
    from slopgate.lint._baseline import Violation

LINT_DETAIL_LIMIT = 3


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


def _candidate_file(ctx: HookContext, candidate: str) -> Path | None:
    if not candidate.lower().endswith(".py"):
        return None
    if is_third_party_or_virtualenv_path(candidate):
        return None
    path = Path(candidate)
    full = path if path.is_absolute() else ctx.config.repo_root / path
    if not full.exists() or not full.is_file():
        return None
    return full.resolve()


def resolve_python_candidates(ctx: HookContext) -> tuple[list[Path], list[Path]]:
    src_files: list[Path] = []
    test_files: list[Path] = []
    for candidate in ctx.candidate_paths:
        full = _candidate_file(ctx, candidate)
        if full is None:
            continue
        normalized = lower_path(str(full))
        if "/tests/" in normalized or full.name.startswith(PYTEST_TEST_PREFIX):
            test_files.append(full)
        else:
            src_files.append(full)
    return (src_files, test_files)


def _touched_reference_test_files(
    src_files: list[Path], test_files: list[Path]
) -> list[Path] | None:
    if not src_files:
        return None
    from slopgate.lint._helpers import test_roots

    by_resolved: dict[Path, Path] = {}
    for tests_root in test_roots():
        if not tests_root.exists():
            continue
        for path in tests_root.rglob("*.py"):
            if path.is_file():
                by_resolved.setdefault(path.resolve(), path)
    for path in test_files:
        by_resolved.setdefault(path.resolve(), path)
    return sorted(by_resolved.values())


def _touched_lint_relative_paths(
    src_files: list[Path], test_files: list[Path]
) -> set[str]:
    from slopgate.lint._helpers import relative_path

    touched = {relative_path(path) for path in [*src_files, *test_files]}
    if src_files:
        touched.add("<project>")
    return touched


def _violation_details(rule_name: str, violations: list[Violation]) -> list[list[str]]:
    from slopgate.lint._details import format_violation_details

    groups = [
        format_violation_details(rule_name, violation, status="HOOK")
        for violation in violations[:LINT_DETAIL_LIMIT]
    ]
    remaining = len(violations) - LINT_DETAIL_LIMIT
    if remaining > 0 and groups:
        groups[-1].append(f"    +{remaining} more {rule_name} violation(s) not shown.")
    return groups


def collect_touched_lint_failures(
    ctx: HookContext,
) -> tuple[list[str], list[list[str]], list[str]]:
    src_files, test_files = resolve_python_candidates(ctx)
    if not src_files and not test_files:
        return ([], [], [])
    from slopgate.lint._collectors import run_touched_collectors
    from slopgate.lint._config import load_config, set_config

    lint_cfg = load_config(ctx.config.repo_root)
    set_config(lint_cfg)
    reference_test_files = _touched_reference_test_files(src_files, test_files)
    touched_paths = _touched_lint_relative_paths(src_files, test_files)
    lint_targets = sorted(path for path in touched_paths if path != "<project>")
    failures: list[str] = []
    details: list[list[str]] = []
    for rule_name, violations in run_touched_collectors(
        src_files, test_files, reference_test_files=reference_test_files
    ):
        scoped = [item for item in violations if item.relative_path in touched_paths]
        if not scoped:
            continue
        failures.append(f"{rule_name}: {len(scoped)}")
        details.extend(_violation_details(rule_name, scoped))
    return (failures, details, lint_targets)


def python_lint_targets(ctx: HookContext) -> list[str]:
    return [
        path
        for path in ctx.candidate_paths
        if path.lower().endswith(".py") and not is_third_party_or_virtualenv_path(path)
    ]


def _lint_detail_text(details: list[list[str]]) -> str:
    if not details:
        return ""
    groups = ["\n".join(group[:12]) for group in details]
    return " Blocking lint collector details:\n" + "\n\n".join(groups)


def _lint_message(
    failures: list[str], details: list[list[str]], targets: list[str]
) -> str:
    target_summary = lint_target_summary(targets)
    instruction = lint_check_instruction(targets)
    message = (
        f"Touched-file lint detectors found issues{target_summary}. "
        f"{preview_with_overflow(failures, limit=QUALITY_FAILURE_PREVIEW_LIMIT)}. "
        f"{instruction} "
        "Repair touched files before continuing."
    )
    message += _lint_detail_text(details)
    if has_oversized_module_failure(failures):
        message = f"{message} {post_lint_oversized_guidance(targets)}"
    return message


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
        failures, details, lint_targets = collect_touched_lint_failures(ctx)
        if not failures:
            return []
        targets = lint_targets or python_lint_targets(ctx)
        message = _lint_message(failures, details, targets)
        metadata: dict[str, object] = {
            "failing_collectors": failures,
            "collector_details": details,
            "paths": targets,
        }
        if targets:
            metadata[METADATA_PATH] = targets[0]
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.HIGH
                if ctx.config.post_edit_quality_block_on_failure
                else Severity.LOW,
                decision=BLOCK
                if ctx.config.post_edit_quality_block_on_failure
                else None,
                message=message
                if ctx.config.post_edit_quality_block_on_failure
                else None,
                additional_context=None
                if ctx.config.post_edit_quality_block_on_failure
                else message,
                metadata=metadata,
            )
        ]
