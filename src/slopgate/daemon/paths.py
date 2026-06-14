"""Shared resident daemon socket paths."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

DEFAULT_DAEMON_SOCKET_NAME = "slopgate-hookd.sock"
LINUX_RUNTIME_ROOT = Path("/run/user")


def default_daemon_socket_path() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / DEFAULT_DAEMON_SOCKET_NAME
    return Path(tempfile.gettempdir()) / _user_scoped_socket_name()


def daemon_socket_path_candidates() -> tuple[Path, ...]:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    candidates: list[Path] = []
    if runtime_dir:
        candidates.append(Path(runtime_dir) / DEFAULT_DAEMON_SOCKET_NAME)
    else:
        linux_runtime_path = _linux_runtime_socket_path()
        if linux_runtime_path is not None:
            candidates.append(linux_runtime_path)
    candidates.append(Path(tempfile.gettempdir()) / _user_scoped_socket_name())
    return tuple(dict.fromkeys(candidates))


def _linux_runtime_socket_path() -> Path | None:
    getuid = getattr(os, "getuid", None)
    if not callable(getuid):
        return None
    runtime_dir = LINUX_RUNTIME_ROOT / str(getuid())
    if not runtime_dir.exists():
        return None
    return runtime_dir / DEFAULT_DAEMON_SOCKET_NAME


def _user_scoped_socket_name() -> str:
    getuid = getattr(os, "getuid", None)
    if callable(getuid):
        return f"slopgate-hookd-{getuid()}.sock"
    return DEFAULT_DAEMON_SOCKET_NAME
