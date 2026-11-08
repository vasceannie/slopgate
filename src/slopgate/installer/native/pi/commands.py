"""Argument-array commands for Pi's native package manager."""

from __future__ import annotations

from pathlib import Path

from slopgate.constants import INSTALL_SCOPE_PROJECT
from slopgate.installer._shared import shell_command
from slopgate.installer.native.commands import NativeCommandError, run_native_command
from slopgate.installer.native.model import NativeRequest
from slopgate.installer.native.pi.identity import PI_EXECUTABLE
from slopgate.installer.native.pi.legacy import pi_agent_dir

__all__ = ["pi_environment", "pi_scope_command", "run_pi_command"]


def pi_environment() -> dict[str, str]:
    """Pin native manager calls to Pi's resolved active agent directory."""
    return {"PI_CODING_AGENT_DIR": str(pi_agent_dir())}


def pi_scope_command(action: str, source: Path, scope: str) -> list[str]:
    """Build a user or project package command; never pass the `both` scope."""
    argv = [PI_EXECUTABLE, action]
    if scope == INSTALL_SCOPE_PROJECT:
        argv.append("-l")
    argv.append(str(source))
    return argv


def run_pi_command(argv: list[str], request: NativeRequest) -> str:
    """Run Pi and surface nonzero native diagnostics without suppressing them."""
    completed = run_native_command(
        argv,
        cwd=request.root,
        platform=PI_EXECUTABLE,
        env=pi_environment(),
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise NativeCommandError(
            f"{shell_command(argv)} exited {completed.returncode}: {detail}"
        )
    return completed.stdout
