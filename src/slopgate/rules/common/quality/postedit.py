"""Post-edit quality gate command execution helpers and rule."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from typing_extensions import override

from slopgate.constants import BLOCK, METADATA_COMMAND, POST_TOOL_USE, SESSION_ID
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled
from slopgate.util.payloads import is_edit_like_tool, is_shell_tool
from slopgate.util.subprocesses import CommandResult, run_shell

from .._shell_read import is_safe_bash_read

if TYPE_CHECKING:
    from slopgate.context import HookContext


_MISSING_EXECUTABLE_PATTERN = re.compile(
    r"(?P<name>[A-Za-z0-9_.+-]+)(?:: command not found|: not found|: not found$)|"
    r"No such file or directory: '(?P<quoted>[^']+)'"
)


@dataclass(frozen=True, slots=True)
class QualityCommandFailure:
    command: str
    returncode: int
    stdout: str
    stderr: str
    missing_executable: str | None = None

    def render(self) -> str:
        body = f"{self.stdout}{self.stderr}".strip()
        return f"$ {self.command}\n[exit {self.returncode}]\n{body}".strip()


def collect_quality_commands(ctx: HookContext) -> list[str]:
    commands: list[str] = []
    for language in sorted(ctx.languages):
        commands.extend(ctx.config.post_edit_quality_commands.get(language, []))
    return commands


def _resolve_quality_cwd(command: str, ctx: HookContext) -> Path | None:
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


def _missing_executable(result: CommandResult) -> str | None:
    if result.returncode != 127:
        return None
    output = f"{result.stderr}\n{result.stdout}"
    match = _MISSING_EXECUTABLE_PATTERN.search(output)
    if match is None:
        return None
    return match.group("name") or match.group("quoted")


def run_quality_commands(
    commands: list[str], ctx: HookContext
) -> list[QualityCommandFailure]:
    failures: list[QualityCommandFailure] = []
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
        if result.returncode == 0:
            continue
        failures.append(
            QualityCommandFailure(
                command=result.command,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                missing_executable=_missing_executable(result),
            )
        )
    return failures


def _should_run_post_edit_quality(ctx: HookContext) -> bool:
    if is_edit_like_tool(ctx.tool_name):
        return True
    if is_shell_tool(ctx.tool_name):
        return not is_safe_bash_read(ctx.tool_name, ctx.shell_command)
    return False


def _render_failure(failure: QualityCommandFailure | str) -> str:
    if isinstance(failure, str):
        return failure
    return failure.render()


def _failure_message(failures: list[QualityCommandFailure | str]) -> str:
    structured = [failure for failure in failures if isinstance(failure, QualityCommandFailure)]
    missing = [failure for failure in structured if failure.missing_executable]
    if missing:
        names = ", ".join(sorted({str(item.missing_executable) for item in missing}))
        rendered = "\n\n".join(_render_failure(item) for item in missing)
        return (
            "Post-edit quality gate could not run because required executable(s) "
            f"were missing: {names}. Repair the environment or configure the "
            f"correct quality command before treating this as code quality.\n\n{rendered}"
        )
    rendered = "\n\n".join(_render_failure(item) for item in failures)
    return f"Post-edit quality gate failed.\n\n{rendered}"


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
        failures = run_quality_commands(collect_quality_commands(ctx), ctx)
        if not failures:
            return []
        message = _failure_message(failures)
        if ctx.config.post_edit_quality_block_on_failure:
            return [
                RuleFinding(
                    rule_id=self.rule_id,
                    title=self.title,
                    severity=Severity.HIGH,
                    decision=BLOCK,
                    message=message,
                )
            ]
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.LOW,
                additional_context=message,
            )
        ]
