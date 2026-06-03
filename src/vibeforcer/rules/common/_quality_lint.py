"""Common Vibeforcer runtime rules."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import TYPE_CHECKING
from typing_extensions import override
from vibeforcer.constants import (
    POST_TOOL_USE,
    PRE_TOOL_USE,
    BLOCK,
    METADATA_COMMAND,
    METADATA_PATH,
    PRODUCTION_SYMBOL_PREVIEW_LIMIT,
    QUALITY_FAILURE_PREVIEW_LIMIT,
)
from vibeforcer.models import RuleFinding, Severity
from vibeforcer.rules.base import Rule, is_rule_enabled
from vibeforcer.util.path_filters import is_third_party_or_virtualenv_path
from vibeforcer.util.payloads import (
    is_edit_like_tool,
    is_shell_tool,
    lower_path,
)
from vibeforcer.util.subprocesses import run_shell
if TYPE_CHECKING:
    from vibeforcer.context import HookContext

from ._shell_read import command_has_word as command_has_word


class SearchReminderRule(Rule):
    rule_id: str = "REMIND-SEARCH-001"
    title: str = "Search reminder"
    events: tuple[str, ...] = (PRE_TOOL_USE,)

    @override
    def evaluate(self, ctx: "HookContext") -> list[RuleFinding]:
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


def _collect_quality_commands(ctx: "HookContext") -> list[str]:
    """Gather post-edit quality commands for detected languages."""
    commands: list[str] = []
    for language in sorted(ctx.languages):
        commands.extend(
            ctx.config.post_edit_quality_commands.get(language, []),
        )
    return commands


def _run_quality_commands(
    commands: list[str],
    ctx: "HookContext",
) -> list[str]:
    """Run each command and return formatted failure descriptions."""
    failures: list[str] = []
    for command in commands:
        formatted = command.format(
            files=" ".join(ctx.candidate_paths),
            first_file=ctx.candidate_paths[0] if ctx.candidate_paths else "",
            language=",".join(sorted(ctx.languages)),
        )
        result = run_shell(formatted, ctx.config.repo_root)
        ctx.trace.subprocess(
            {
                "event_name": ctx.event_name,
                "session_id": ctx.session_id,
                METADATA_COMMAND: result.command,
                "cwd": result.cwd,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        if result.returncode != 0:
            desc = (
                f"$ {result.command}\n"
                f"[exit {result.returncode}]\n"
                f"{result.stdout}{result.stderr}"
            ).strip()
            failures.append(desc)
    return failures


class PostEditQualityRule(Rule):
    rule_id: str = "QUALITY-POST-001"
    title: str = "Post-edit quality gate"
    events: tuple[str, ...] = (POST_TOOL_USE,)

    @override
    def evaluate(self, ctx: "HookContext") -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        if not ctx.config.post_edit_quality_enabled or not ctx.languages:
            return []
        commands = _collect_quality_commands(ctx)
        if not commands:
            return []
        failures = _run_quality_commands(commands, ctx)
        if not failures:
            return []
        joined = "\n\n".join(failures)
        if ctx.config.post_edit_quality_block_on_failure:
            return [
                RuleFinding(
                    rule_id=self.rule_id,
                    title=self.title,
                    severity=Severity.HIGH,
                    decision=BLOCK,
                    message=f"Post-edit quality gate failed.\n\n{joined}",
                )
            ]
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.LOW,
                additional_context=f"Post-edit quality failures:\n\n{joined}",
            )
        ]


def _resolve_python_candidates(ctx: "HookContext") -> tuple[list[Path], list[Path]]:
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
        if "/tests/" in normalized or full.name.startswith("test_"):
            test_files.append(full)
        else:
            src_files.append(full)
    return src_files, test_files


def _touched_reference_test_files(src_files: list[Path], test_files: list[Path]) -> list[Path] | None:
    """Return suite test references when touched source files need coverage context."""
    if not src_files:
        return None
    from vibeforcer.lint._helpers import tests_root

    by_resolved = {path.resolve(): path for path in tests_root().rglob("*.py") if path.is_file()}
    for path in test_files:
        by_resolved.setdefault(path.resolve(), path)
    return sorted(by_resolved.values())


def _touched_lint_relative_paths(src_files: list[Path], test_files: list[Path]) -> set[str]:
    """Return relative lint paths allowed to report from a post-edit hook."""
    from vibeforcer.lint._helpers import relative_path

    touched = {relative_path(path) for path in [*src_files, *test_files]}
    if src_files:
        touched.add("<project>")
    return touched


def _collect_touched_lint_failures(
    ctx: "HookContext",
) -> tuple[list[str], list[str], list[str]]:
    src_files, test_files = _resolve_python_candidates(ctx)
    if not src_files and not test_files:
        return [], [], []
    from vibeforcer.lint._collectors import run_touched_collectors
    from vibeforcer.lint._config import load_config as load_lint_config
    from vibeforcer.lint._config import set_config as set_lint_config
    from vibeforcer.lint._details import format_violation_details

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


def _python_lint_targets(ctx: "HookContext") -> list[str]:
    return [
        path
        for path in ctx.candidate_paths
        if path.lower().endswith(".py")
        and not is_third_party_or_virtualenv_path(path)
    ]


def _lint_target_summary(paths: list[str]) -> str:
    if not paths:
        return ""
    shown = ", ".join(paths[:3])
    if len(paths) > 3:
        shown += f", +{len(paths) - 3} more"
    return f" for {shown}"


def _lint_check_instruction(paths: list[str]) -> str:
    command = "from the repo root, run `vibeforcer lint check`"
    if not paths:
        return f"Run {command} for details."
    shown = ", ".join(shlex.quote(path) for path in paths[:PRODUCTION_SYMBOL_PREVIEW_LIMIT])
    return (
        f"Touched lint candidates: {shown}. {command}; "
        "the command intentionally accepts no file/path argument."
    )


_OVERSIZED_LINT_RULES = ("oversized-module", "oversized-module-soft")


def _has_oversized_module_failure(failures: list[str]) -> bool:
    return any(item.startswith(rule + ":") for item in failures for rule in _OVERSIZED_LINT_RULES)


def _first_lint_path(paths: list[str]) -> str:
    return paths[0] if paths else "<touched .py file>"


def _lint_split_scenario(path_value: str) -> str:
    normalized = path_value.replace("\\", "/").lower()
    name = normalized.rsplit("/", 1)[-1]
    if name == "conftest.py":
        return "conftest"
    if name == "__init__.py":
        return "package-init"
    if name.startswith("test_") or normalized.startswith("tests/") or "/tests/" in normalized:
        return "test-module"
    if name in {"cli.py", "main.py", "app.py"} or normalized.endswith("/routes.py"):
        return "entrypoint-or-router"
    return "module-to-package"


_DEFAULT_SPLIT_DETAIL = (
    "Module/package split: convert module.py into module/__init__.py plus focused "
    "siblings; re-export the old public API; split into models/types, parsing, "
    "services/orchestration, adapters/IO, constants/data, and errors."
)

_SPLIT_SCENARIO_DETAILS = {
    "conftest": (
        "Conftest split: keep conftest.py as a thin fixture registry; move "
        "factories, fake clients/apps, pilot/wait helpers, and assertion helpers "
        "into tests/<area>/support/ modules; move subtree-only fixtures into "
        "that subtree's conftest.py."
    ),
    "package-init": (
        "Package-init split: make __init__.py facade-only with __all__ and "
        "compatibility re-exports; move implementation and import-time side "
        "effects into sibling modules."
    ),
    "test-module": (
        "Test-module split: split by behavior under test; move reusable "
        "factories/fakes/assertion helpers to support modules; use pytest "
        "parametrization for repeated scenarios."
    ),
    "entrypoint-or-router": (
        "Entrypoint/router split: keep commands/routes thin; move orchestration "
        "to services, schemas/models to dedicated modules, and IO adapters to edges."
    ),
}


def _post_lint_split_detail(scenario: str) -> str:
    return _SPLIT_SCENARIO_DETAILS.get(scenario, _DEFAULT_SPLIT_DETAIL)


def _post_lint_oversized_guidance(paths: list[str]) -> str:
    target = _first_lint_path(paths)
    scenario = _lint_split_scenario(target)
    return (
        f"Oversized-module recovery: use the {scenario} split plan before continuing. "
        f"{_post_lint_split_detail(scenario)} "
        "Line-count camouflage is not recovery: do not delete blank lines, compress "
        "formatting, or shuffle comments just to duck the threshold; ruff/formatters "
        "will normalize style while the oversized-module design smell remains. "
        "If the file is mostly generated data or giant literals, move data into "
        "resources, fixtures, or builders instead of hiding it in Python code. "
        f"Verify with `python3 -m py_compile {target}` plus the smallest focused tests."
    )


class PostEditLintRule(Rule):
    rule_id: str = "QUALITY-LINT-001"
    title: str = "Touched-file lint advisory"
    events: tuple[str, ...] = (POST_TOOL_USE,)

    @override
    def evaluate(self, ctx: "HookContext") -> list[RuleFinding]:
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
