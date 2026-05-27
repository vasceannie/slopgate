from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_WINDOWS_UNC_RE = re.compile(r"^\\\\[^\\]+\\[^\\]+")


def is_windows() -> bool:
    return sys.platform == "win32" or os.name == "nt"


def user_config_dir(app_name: str) -> Path:
    if is_windows():
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / app_name
        return Path.home() / "AppData" / "Roaming" / app_name
    xdg_config_home = os.getenv("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / app_name
    return Path.home() / ".config" / app_name


def user_data_dir(app_name: str) -> Path:
    if is_windows():
        local_appdata = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if local_appdata:
            return Path(local_appdata) / app_name
    return Path.home() / ".local" / "share" / app_name


def normalize_path_for_match(value: str) -> str:
    return value.replace("\\", "/").strip()


def lower_path_for_match(value: str) -> str:
    return normalize_path_for_match(value).lower()


def looks_like_windows_absolute_path(value: str) -> bool:
    stripped = value.strip()
    return bool(_WINDOWS_DRIVE_RE.match(stripped) or _WINDOWS_UNC_RE.match(stripped))


def resolve_path_for_match(path_value: str, cwd: Path) -> str:
    expanded = path_value.strip()
    if looks_like_windows_absolute_path(expanded):
        return lower_path_for_match(expanded)
    path = Path(expanded).expanduser()
    if not path.is_absolute():
        path = cwd / path
    return lower_path_for_match(str(path.resolve(strict=False)))
