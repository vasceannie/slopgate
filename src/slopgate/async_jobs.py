from __future__ import annotations

from collections.abc import Mapping

from slopgate.constants import METADATA_COMMAND, POST_TOOL_USE, SESSION_ID
from slopgate.context import build_context
from slopgate.util.subprocesses import run_shell


def run_async_jobs(payload_dict: Mapping[str, object]) -> tuple[str, list[str]]:
    ctx = build_context(payload_dict)
    if (
        ctx.event_name != POST_TOOL_USE
        or not ctx.config.async_jobs_enabled
        or not ctx.languages
    ):
        return ("", [])
    commands: list[str] = []
    for language in sorted(ctx.languages):
        commands.extend(ctx.config.async_jobs_commands.get(language, []))
    if not commands:
        return ("", [])
    summaries: list[str] = []
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
                SESSION_ID: ctx.session_id,
                METADATA_COMMAND: result.command,
                "cwd": result.cwd,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            async_mode=True,
        )
        status = "PASS" if result.returncode == 0 else "FAIL"
        output = (result.stdout + result.stderr).strip()
        if output:
            summaries.append(f"[{status}] {result.command}\n{output}")
        else:
            summaries.append(f"[{status}] {result.command}")
    return ("\n\n".join(summaries), [])
