"""Shared resident daemon socket paths."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

DEFAULT_DAEMON_SOCKET_NAME = "slopgate-hookd.sock"


def default_daemon_socket_path() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / DEFAULT_DAEMON_SOCKET_NAME
    return Path(tempfile.gettempdir()) / _user_scoped_socket_name()


def _user_scoped_socket_name() -> str:
    getuid = getattr(os, "getuid", None)
    if callable(getuid):
        return f"slopgate-hookd-{getuid()}.sock"
    return DEFAULT_DAEMON_SOCKET_NAME
