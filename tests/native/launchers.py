"""Platform-correct Python launchers for fake native managers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_POSIX_MODE = 0o755
_WINDOWS_SCRIPT_SUFFIX = ".py"
_WINDOWS_LAUNCHER_SUFFIX = ".cmd"


def write_python_launcher(directory: Path, name: str, body: str) -> Path:
    """Write a runnable Python fake named *name* and return its executable path."""
    directory.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        return _write_windows_launcher(directory, name, body)
    return _write_posix_launcher(directory, name, body)


def _write_posix_launcher(directory: Path, name: str, body: str) -> Path:
    executable = directory / name
    executable.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    executable.chmod(_POSIX_MODE)
    return executable


def _write_windows_launcher(directory: Path, name: str, body: str) -> Path:
    script = directory / f"{name}{_WINDOWS_SCRIPT_SUFFIX}"
    script.write_text(body, encoding="utf-8")
    launcher = directory / f"{name}{_WINDOWS_LAUNCHER_SUFFIX}"
    launcher.write_text(
        f'@echo off\r\n"{sys.executable}" "%~dp0{script.name}" %*\r\n',
        encoding="utf-8",
    )
    return launcher
