"""Common Slopgate runtime rules."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from typing_extensions import override
from slopgate.constants import (
    POST_TOOL_USE,
    PRE_TOOL_USE,
    BLOCK,
    METADATA_PATH,
    PYTEST_TEST_PREFIX,
    QUALITY_FAILURE_PREVIEW_LIMIT,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled
from slopgate.util.path_filters import is_third_party_or_virtualenv_path
from slopgate.util.payloads import (
    is_edit_like_tool,
    is_shell_tool,
    lower_path,
)
if TYPE_CHECKING:
    from slopgate.context import HookContext

from ._quality_lint_guidance import (
    _has_oversized_module_failure,
    _lint_check_instruction,
    _lint_target_summary,
    _post_lint_oversized_guidance,
)
from ._quality_postedit import (
    PostEditQualityRule,
    _collect_quality_commands,
    _run_quality_commands,
)
from ._shell_read import _is_safe_bash_read as _is_safe_bash_read
from ._shell_read import command_has_word as command_has_word


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


def _resolve_python_candidates(ctx: HookContext) -> tuple[list[Path], list[Path]]:
    src_files: list[Path] = []
    test_files: list[Path] = []
    for candidate in ctx.candidate_paths:
        if not candidate.lower().endswith(".py"):
            continue
        if is_third_party_or_virtualenv_path(candidate):
            continue
        full = (
            (ctx.config.repo_root / candidate).resolve()
            if not Path(candidate).is_absolute()
            else Path(candidate)
        )
        if not full.exists() or not full.is_file():
            continue
        normalized = lower_path(str(full))
        if "/tests/" in normalized or full.name.startswith(PYTEST_TEST_PREFIX):
            test_files.append(full)
        else:
            src_files.append(full)
    return src_files, test_files


def _touched_reference_test_files(src_files: list[Path], test_files: list[Path]) -> list[Path] | None:
    """Return suite test references when touched source files need coverage context."""
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


def _touched_lint_relative_paths(src_files: list[Path], test_files: list[Path]) -> set[str]:
    """Return relative lint paths allowed to report from a post-edit hook."""
    from slopgate.lint._helpers import relative_path

    touched = {relative_path(path) for path in [*src_files, *test_files]}
    if src_files:
        touched.add("<project>")
    return touched


def _collect_touched_lint_failures(
    ctx: HookContext,
) -> tuple[list[str], list[str], list[str]]:
    src_files, test_files = _resolve_python_candidates(ctx)
    if not src_files and not test_files:
        return [], [], []
    from slopgate.lint._collectors import run_touched_collectors
    from slopgate.lint._config import load_config as load_lint_config
    from slopgate.lint._config import set_config as set_lint_config
    from slopgate.lint._details import format_violation_details

    lint_cfg = load_lint_config(ctx.config.repo_root)
    set_lint_config(lint_cfg)
    reference_test_files = _touched_reference_test_files(src_files, test_files)
    touched_paths = _touched_lint_relative_paths(src_files, test_files)
    lint_targets = sorted(path for path in touched_paths if path != "<project>")
    failures: list[str] = []
    first_detail: list[str] = []
    for rule_name, violations in run_touched_collectors(
        src_files,
        test_files,
        reference_test_files=reference_test_files,
    ):
        scoped_violations = [
            violation
            for violation in violations
            if violation.relative_path in touched_paths
        ]
        if not scoped_violations:
            continue
        failures.append(f"{rule_name}: {len(scoped_violations)}")
        if not first_detail:
            first_detail = format_violation_details(
                rule_name,
                scoped_violations[0],
                status="HOOK",
            )
    return failures, first_detail, lint_targets


def _python_lint_targets(ctx: HookContext) -> list[str]:
    return [
        path
        for path in ctx.candidate_paths
        if path.lower().endswith(".py")
        and not is_third_party_or_virtualenv_path(path)
    ]


class PostEditLintRule(Rule):
    rule_id: str = "QUALITY-LINT-001"
    title: str = "Touched-file lint advisory"
    events: tuple[str, ...] = (POST_TOOL_USE,)

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        if not (is_edit_like_tool(ctx.tool_name) or is_shell_tool(ctx.tool_name)):
            return []
        failures, first_detail, lint_targets = _collect_touched_lint_failures(ctx)
        if not failures:
            return []
        summary = ", ".join(failures[:QUALITY_FAILURE_PREVIEW_LIMIT])
        if len(failures) > QUALITY_FAILURE_PREVIEW_LIMIT:
            summary += f", +{len(failures) - QUALITY_FAILURE_PREVIEW_LIMIT} more"
        targets = lint_targets or _python_lint_targets(ctx)
        target_summary = _lint_target_summary(targets)
        instruction = _lint_check_instruction(targets)
        details = (
            f"Touched-file lint detectors found issues{target_summary}. "
            f"{summary}. {instruction} Repair touched files before continuing."
        )
        if first_detail:
            details = (
                f"{details} First lint violation detail:\n"
                + "\n".join(first_detail[:12])
            )
        if _has_oversized_module_failure(failures):
            details = f"{details} {_post_lint_oversized_guidance(targets)}"
        metadata: dict[str, object] = {"failing_collectors": failures, "paths": targets}
        if targets:
            metadata[METADATA_PATH] = targets[0]
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=(
                    Severity.HIGH
                    if ctx.config.post_edit_quality_block_on_failure
                    else Severity.LOW
                ),
                decision=(
                    BLOCK if ctx.config.post_edit_quality_block_on_failure else None
                ),
                message=details if ctx.config.post_edit_quality_block_on_failure else None,
                additional_context=(
                    None if ctx.config.post_edit_quality_block_on_failure else details
                ),
                metadata=metadata,
            )
        ]
