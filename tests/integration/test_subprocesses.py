from __future__ import annotations

from pathlib import Path

from vibeforcer.util.subprocesses import CommandResult, run_shell


def test_run_shell_executes_command_from_requested_working_directory(
    tmp_path: Path,
) -> None:
    result = run_shell("pwd", tmp_path, timeout=5)

    assert result == CommandResult(
        command="pwd",
        cwd=str(tmp_path),
        returncode=0,
        stdout=f"{tmp_path}\n",
        stderr="",
    )
