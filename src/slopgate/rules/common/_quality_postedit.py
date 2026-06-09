"""Post-edit quality gate command execution helpers and rule."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from typing_extensions import override
from slopgate.constants import (
    POST_TOOL_USE,
    SESSION_ID,
    BLOCK,
    METADATA_COMMAND,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled
from slopgate.util.payloads import is_edit_like_tool, is_shell_tool
from slopgate.util.subprocesses import run_shell

if TYPE_CHECKING:
    from slopgate.context import HookContext

from ._shell_read import _is_safe_bash_read as _is_safe_bash_read


def _collect_quality_commands(ctx: HookContext) -> list[str]:
    """Gather post-edit quality commands for detected languages."""
    commands: list[str] = []
    for language in sorted(ctx.languages):
        commands.extend(
            ctx.config.post_edit_quality_commands.get(language, []),
        )
    return commands


def _resolve_quality_cwd(command: str, ctx: HookContext) -> Path | None:
    """Resolve the working directory for a quality command.

    For commands that operate on a project manifest (npm, cargo), walk up
    from the first candidate path to find the nearest manifest — the command
    may need to run from a project subdirectory rather than repo root.
    Returns None when no valid manifest is found, causing the caller to
    skip the quality command rather than running it from a wrong directory.
    """
    if not ctx.candidate_paths:
        return ctx.config.repo_root
    first = Path(ctx.candidate_paths[0])
    if not first.is_absolute():
        first = ctx.config.repo_root / first
    command_lower = command.lower().strip()
    if command_lower.startswith("npm") or command_lower.startswith("npx"):
        manifest_name = "package.json"
    elif command_lower.startswith("cargo"):
        manifest_name = "Cargo.toml"
    else:
        return ctx.config.repo_root
    for parent in [first, *first.parents]:
        if (parent / manifest_name).exists():
            return parent
    if (ctx.config.repo_root / manifest_name).exists():
        return ctx.config.repo_root
    return None


def _run_quality_commands(
    commands: list[str],
    ctx: HookContext,
) -> list[str]:
    """Run each command and return formatted failure descriptions."""
    failures: list[str] = []
    for command in commands:
        formatted = command.format(
            files=" ".join(ctx.candidate_paths),
            first_file=ctx.candidate_paths[0] if ctx.candidate_paths else "",
            language=",".join(sorted(ctx.languages)),
        )
        cwd = _resolve_quality_cwd(command, ctx)
        if cwd is None:
            ctx.trace.subprocess(
                {
                    "event_name": ctx.event_name,
                    SESSION_ID: ctx.session_id,
                    METADATA_COMMAND: formatted,
                    "cwd": None,
                    "returncode": None,
                    "stdout": "",
                    "stderr": f"Skipped: no valid manifest for {command}",
                }
            )
            continue
        result = run_shell(formatted, cwd)
        ctx.trace.subprocess(
            {
                "event_name": ctx.event_name,
                SESSION_ID: ctx.session_id,
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


def _should_run_post_edit_quality(ctx: HookContext) -> bool:
    """Return True when a PostToolUse event plausibly changed project files."""
    if is_edit_like_tool(ctx.tool_name):
        return True
    if is_shell_tool(ctx.tool_name):
        return not _is_safe_bash_read(ctx.tool_name, ctx.shell_command)
    return False


class PostEditQualityRule(Rule):
    rule_id: str = "QUALITY-POST-001"
    title: str = "Post-edit quality gate"
    events: tuple[str, ...] = (POST_TOOL_USE,)

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        if not _should_run_post_edit_quality(ctx):
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
