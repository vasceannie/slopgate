"""Argument-array execution of native harness package-manager commands."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

from slopgate.util import logger
from slopgate.util.platform import child_creation_flags

NATIVE_COMMAND_TIMEOUT_SECONDS = 120
LIST_SUBCOMMAND = "list"
REMOVE_SUBCOMMAND = "remove"


__all__ = [
    "LIST_SUBCOMMAND",
    "NATIVE_COMMAND_TIMEOUT_SECONDS",
    "NativeCommandError",
    "REMOVE_SUBCOMMAND",
    "native_executable_available",
    "run_native_command",
]


class NativeCommandError(RuntimeError):
    """A native manager could not be started, timed out, or is missing."""


def native_executable_available(executable: str) -> bool:
    """Return whether a native manager executable resolves on PATH."""
    return shutil.which(executable) is not None


def _native_env(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    env.pop("FORCE_COLOR", None)
    env.update(overrides or {})
    return env


def _failure(
    message: str, argv: list[str], cwd: Path, platform: str, **fields: str
) -> NativeCommandError:
    logger.warning(
        message,
        platform=platform,
        action=" ".join(argv[1:3]),
        cwd=str(cwd),
        **fields,
    )
    return NativeCommandError(f"{message}: {' '.join(argv)}")


_EMPTY_TIMEOUT_STREAM = "<empty>"


def _timeout_stream(value: str | bytes | None) -> str:
    text = (
        value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
    )
    return text or _EMPTY_TIMEOUT_STREAM


def _timeout_failure(
    exc: subprocess.TimeoutExpired, argv: list[str], cwd: Path, platform: str
) -> NativeCommandError:
    message = f"{platform} command timed out after {NATIVE_COMMAND_TIMEOUT_SECONDS}s"
    failure = _failure(message, argv, cwd, platform)
    streams = (
        f"stdout: {_timeout_stream(exc.stdout)}; stderr: {_timeout_stream(exc.stderr)}"
    )
    return NativeCommandError(f"{failure} ({streams})")


def run_native_command(
    argv: list[str], *, cwd: Path, platform: str, env: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run one native manager command without a shell and capture its output.

    Nonzero exits are returned to the caller because a native manager can
    partially mutate state before failing; only inability to run the command
    raises ``NativeCommandError``.
    """
    resolved = shutil.which(argv[0])
    if resolved is None:
        raise _failure(
            f"{argv[0]} was not found on PATH (install the {platform} CLI)",
            argv,
            cwd,
            platform,
        )
    try:
        completed = subprocess.run(
            [resolved, *argv[1:]],
            env=_native_env(env),
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=NATIVE_COMMAND_TIMEOUT_SECONDS,
            creationflags=child_creation_flags(),
        )
    except subprocess.TimeoutExpired as exc:
        raise _timeout_failure(exc, argv, cwd, platform) from exc
    except OSError as exc:
        raise _failure(
            f"{platform} command could not start ({exc})", argv, cwd, platform
        ) from exc
    logger.info(
        "installer native command finished",
        platform=platform,
        action=" ".join(argv[1:3]),
        cwd=str(cwd),
        returncode=completed.returncode,
    )
    return completed
