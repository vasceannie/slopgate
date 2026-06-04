from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from slopgate.util.platform import is_windows


@dataclass(slots=True)
class CommandResult:
    command: str
    cwd: str
    returncode: int
    stdout: str
    stderr: str


def _configured_shell() -> str:
    configured = os.getenv("SLOPGATE_COMMAND_SHELL", "").strip().lower()
    if configured:
        return configured
    return "powershell" if is_windows() else "native"


def _powershell_executable() -> str:
    return shutil.which("pwsh") or shutil.which("powershell") or "powershell"


def run_shell(command: str, cwd: Path, timeout: int = 120) -> CommandResult:
    shell_kind = _configured_shell()
    if shell_kind in {"powershell", "pwsh"}:
        completed = subprocess.run(
            [
                _powershell_executable(),
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                command,
            ],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    else:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    return CommandResult(
        command=command,
        cwd=str(cwd),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
