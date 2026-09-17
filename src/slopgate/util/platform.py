from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_WINDOWS_UNC_RE = re.compile(r"^\\\\[^\\]+\\[^\\]+")


def is_windows() -> bool:
    return sys.platform == "win32" or os.name == "nt"


# Windows process creation flag that runs a console application without
# allocating a console window. Windows ignores it for non-console
# applications and when combined with CREATE_NEW_CONSOLE or DETACHED_PROCESS.
# https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags
CREATE_NO_WINDOW = 0x08000000


def child_creation_flags() -> int:
    """Return creation flags that stop Windows allocating a console for a child.

    Zero everywhere else: ``subprocess`` rejects a non-zero ``creationflags``
    on POSIX, so callers can pass the result unconditionally.
    """
    return CREATE_NO_WINDOW if is_windows() else 0


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
    stripped = value.strip()
    if not stripped:
        return ""
    return stripped.replace("\\", "/")


def lower_path_for_match(value: str) -> str:
    normalized = normalize_path_for_match(value)
    if not normalized:
        return ""
    return "/".join(part.casefold() for part in normalized.split("/"))


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
