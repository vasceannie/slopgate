"""Argument-array commands for Pi's native package manager."""

from __future__ import annotations

import re
from pathlib import Path

from slopgate.constants import INSTALL_SCOPE_PROJECT
from slopgate.installer._shared import shell_command
from slopgate.installer.native.commands import NativeCommandError, run_native_command
from slopgate.installer.native.model import NativeRequest
from slopgate.installer.native.pi.identity import PI_EXECUTABLE
from slopgate.installer.native.pi.legacy import pi_agent_dir

__all__ = [
    "PI_MINIMUM_VERSION",
    "PI_MINIMUM_VERSION_TEXT",
    "PI_VERSION_COMMAND",
    "pi_environment",
    "pi_scope_command",
    "require_supported_pi_version",
    "run_pi_command",
]

# First Pi release whose extension loader provides the @earendil-works/* modules
# the staged package imports; 0.73.x and earlier only expose @mariozechner/*.
PI_MINIMUM_VERSION = (0, 74, 0)
PI_MINIMUM_VERSION_TEXT = ".".join(str(part) for part in PI_MINIMUM_VERSION)
PI_VERSION_COMMAND: tuple[str, ...] = (PI_EXECUTABLE, "--version")
# `pi --version` prints only the version; anything else is not a version we can trust.
# SemVer 2.0 grammar: ASCII digits only, no leading zeros, no empty identifiers.
_SEMVER_NUMBER = r"(?:0|[1-9][0-9]*)"
_SEMVER_PRERELEASE_ID = rf"(?:{_SEMVER_NUMBER}|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
_PI_VERSION_PATTERN = re.compile(
    rf"({_SEMVER_NUMBER})\.({_SEMVER_NUMBER})\.({_SEMVER_NUMBER})"
    rf"(?P<prerelease>-{_SEMVER_PRERELEASE_ID}(?:\.{_SEMVER_PRERELEASE_ID})*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


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


def require_supported_pi_version(request: NativeRequest) -> None:
    """Refuse Pi releases that would register the package but fail to load it."""
    argv = list(PI_VERSION_COMMAND)
    output = run_pi_command(argv, request)
    match = _PI_VERSION_PATTERN.fullmatch(output.strip())
    if match is None:
        raise NativeCommandError(
            f"Could not read a Pi version from `{shell_command(argv)}`: "
            f"{output.strip()!r}. Existing enforcement was left unchanged."
        )
    if not _meets_minimum(match):
        raise NativeCommandError(
            f"Pi {match.group(0)} cannot load Slopgate's package, which imports "
            f"@earendil-works/pi-tui; upgrade Pi to {PI_MINIMUM_VERSION_TEXT} or "
            "newer. Existing enforcement was left unchanged."
        )


def _meets_minimum(match: re.Match[str]) -> bool:
    """Compare by semver precedence: a pre-release sorts below its final release."""
    core = tuple(int(part) for part in match.group(1, 2, 3))
    is_final = match.group("prerelease") is None
    return (core, is_final) >= (PI_MINIMUM_VERSION, True)
