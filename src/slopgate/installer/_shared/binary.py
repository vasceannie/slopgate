"""Binary discovery and hook command formatting."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from slopgate.constants import METADATA_SLOPGATE, PLATFORM_CLAUDE
from slopgate.installer.hook_proxy import posix_daemon_proxy_command
from slopgate.util import logger
from slopgate.util.platform import is_windows

HOOK_TIMEOUT_SHORT = 10
HOOK_TIMEOUT_STANDARD = HOOK_TIMEOUT_SHORT + HOOK_TIMEOUT_SHORT
HOOK_TIMEOUT_LONG = HOOK_TIMEOUT_STANDARD + HOOK_TIMEOUT_SHORT
_BINARY_PROBE_TIMEOUT_SECONDS = 5


def find_binary() -> str:
    """Find a runnable slopgate binary on PATH."""
    binary = shutil.which(METADATA_SLOPGATE)
    if not binary:
        return sys.executable
    return binary if _binary_is_runnable(binary) else sys.executable


def _binary_is_runnable(binary: str) -> bool:
    try:
        completed = subprocess.run(
            [binary, "--version"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=_BINARY_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning(
            "installer slopgate binary probe failed",
            binary=binary,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return False
    if completed.returncode == 0:
        return True
    logger.warning(
        "installer slopgate binary probe returned nonzero",
        binary=binary,
        returncode=completed.returncode,
    )
    return False


def base_invocation(binary: str) -> list[str]:
    if Path(binary).resolve() == Path(sys.executable).resolve():
        return [binary, "-m", METADATA_SLOPGATE]
    return [binary]


def shell_command(argv: list[str], *, windows: bool | None = None) -> str:
    use_windows = is_windows() if windows is None else windows
    if not use_windows:
        return shlex.join(argv)
    ps_args = ["'" + arg.replace("'", "''") + "'" for arg in argv]
    ps_script = "& " + " ".join(ps_args)
    return subprocess.list2cmdline(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps_script,
        ]
    )


def hook_command(binary: str, *args: str, windows: bool | None = None) -> str:
    fallback_argv = [*base_invocation(binary), *args]
    use_windows = is_windows() if windows is None else windows
    if use_windows:
        return shell_command(fallback_argv, windows=True)
    return posix_daemon_proxy_command(
        fallback_argv, _platform_from_hook_args(args), shell_command
    )


def _platform_from_hook_args(args: tuple[str, ...]) -> str:
    for index, token in enumerate(args):
        if token == "--platform" and index + 1 < len(args):
            return args[index + 1]
    return PLATFORM_CLAUDE
