"""Path bridge for a native plugin CLI that runs inside WSL.

A Windows machine can put a ``claude.bat`` on PATH containing ``wsl claude %*``.
The CLI then is a Linux program: it rejects ``C:\\...`` sources, reports
``/mnt/c/...`` paths and keeps its user settings in the WSL home directory.
Everything Slopgate reads back from that CLI crosses this bridge, inside the
distribution and user the shim selects (``wsl -d <name> -u <user>``) or WSL's
defaults.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from slopgate.constants import REPLACE
from slopgate.installer.native.commands import NativeCommandError, run_native_command
from slopgate.util.platform import is_windows

WSL_EXECUTABLE = "wsl"
_WSL_PLATFORM = "wsl"
_SHIM_SUFFIXES = frozenset({".bat", ".cmd"})
# ``wsl``/``wsl.exe``, bare or by path; a quoted path may contain spaces.
_WSL_INVOCATION = (
    r"^@?\s*(?:call\s+)?"
    r'(?:"(?:[^"]*[\\/])?wsl(?:\.exe)?"|(?:[^\s"]*[\\/])?wsl(?:\.exe)?)\s+'
)
# Options that choose where the shim's command runs; every bridge call repeats
# them so it reads the same distribution and user home as the CLI itself.
_TARGET_FLAGS = frozenset({"-d", "--distribution", "--distribution-id", "-u", "--user"})
# One command-line argument: whitespace separates arguments except inside
# double quotes, which only group (an unterminated quote runs to the end).
_ARGUMENT = re.compile(r'(?:"[^"]*"?|[^\s"]+)+')
_OTHER_VALUE_FLAGS = frozenset({"--cd", "--shell-type"})
_END_OF_OPTIONS = frozenset({"-e", "--exec", "--"})
_HOME_DIRECTORY_ARG = "~"
_WSLPATH_TO_WINDOWS = "-w"
_CONFIG_DIR_SCRIPT = 'printf %s "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"'

__all__ = ["WslPaths", "WslShim", "read_wsl_shim", "wsl_paths_for"]


@dataclass(frozen=True, slots=True)
class WslShim:
    """A batch file that forwards its command into WSL."""

    target: tuple[str, ...]
    """``wsl`` options selecting the shim's distribution and user; empty = defaults."""


def read_wsl_shim(script: Path) -> WslShim | None:
    """The shim ``script`` is when a command line runs ``wsl ... <name>``.

    The invocation must start a line (after ``@``/``call``), so comments, echoed
    messages and conditional wrappers that merely mention ``wsl`` are not shims.
    """
    if script.suffix.lower() not in _SHIM_SUFFIXES:
        return None
    try:
        lines = script.read_text(encoding="utf-8", errors=REPLACE).splitlines()
    except OSError:
        return None
    forwards = re.compile(
        _WSL_INVOCATION + r"(?P<arguments>.*\b" + re.escape(script.stem) + r"\b.*)$",
        re.IGNORECASE,
    )
    for line in lines:
        match = forwards.match(line.strip())
        if match is not None:
            return WslShim(_target_options(match.group("arguments")))
    return None


def _target_options(arguments: str) -> tuple[str, ...]:
    """The distribution/user options among the ``wsl`` options before the command."""
    tokens = iter(token.replace('"', "") for token in _ARGUMENT.findall(arguments))
    target: list[str] = []
    for flag in tokens:
        if flag == _HOME_DIRECTORY_ARG:
            continue
        if flag in _END_OF_OPTIONS or not flag.startswith("-"):
            break
        value = next(tokens, None)
        if flag in _TARGET_FLAGS and value is not None:
            target.extend((flag, value))
        elif flag not in _OTHER_VALUE_FLAGS:
            break
    return tuple(target)


def wsl_paths_for(executable: str, cwd: Path) -> WslPaths | None:
    """A bridge when ``executable`` resolves to a WSL-forwarding shim on Windows."""
    if not is_windows():
        return None
    resolved = shutil.which(executable)
    if resolved is None:
        return None
    shim = read_wsl_shim(Path(resolved))
    if shim is None:
        return None
    return WslPaths(cwd, shim.target)


class WslPaths:
    """Translate the paths a WSL-hosted CLI reports into Windows paths."""

    def __init__(self, cwd: Path, target: tuple[str, ...] = ()) -> None:
        self._cwd = cwd
        self._target = target
        self._cache: dict[str, str] = {}

    def to_windows(self, wsl_path: str) -> Path:
        """Windows path for a WSL path; anything not WSL-absolute is unchanged."""
        if not wsl_path.startswith("/"):
            return Path(wsl_path)
        if wsl_path not in self._cache:
            self._cache[wsl_path] = self._wsl_output(
                ["wslpath", _WSLPATH_TO_WINDOWS, wsl_path]
            )
        return Path(self._cache[wsl_path])

    def claude_config_dir(self) -> Path:
        """The WSL Claude config directory as a path Windows can open."""
        return self.to_windows(self._wsl_output(["sh", "-c", _CONFIG_DIR_SCRIPT]))

    def _wsl_output(self, argv: list[str]) -> str:
        command = [WSL_EXECUTABLE, *self._target, "-e", *argv]
        completed = run_native_command(command, cwd=self._cwd, platform=_WSL_PLATFORM)
        output = completed.stdout.strip()
        if completed.returncode != 0 or not output:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise NativeCommandError(
                f"{' '.join(command)} exited {completed.returncode}: {detail}"
            )
        return output
