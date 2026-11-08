"""Read Pi's native package sources without rewriting host settings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from slopgate.constants import INSTALL_SCOPE_PROJECT, INSTALL_SCOPE_USER
from slopgate.installer.native.model import LegacyRefusal, SOURCE_KEY
from slopgate.installer.native.pi.legacy import pi_agent_dir

__all__ = [
    "PackageEntry",
    "package_entries",
    "project_settings_path",
    "registered_entry",
    "resolve_source",
    "settings_directory",
    "settings_path",
    "user_settings_path",
]

_SETTINGS_FILE_NAME = "settings.json"
_PROJECT_CONFIG_DIR = ".pi"
_PACKAGES_KEY = "packages"


@dataclass(frozen=True, slots=True)
class PackageEntry:
    """One Pi package source as stored by Pi, including opaque resource filters."""

    raw: object
    source: str
    resolved: Path
    filtered: bool


def user_settings_path() -> Path:
    """Return Pi's active user settings path."""
    return pi_agent_dir() / _SETTINGS_FILE_NAME


def project_settings_path(root: Path) -> Path:
    """Return project-local Pi settings for a resolved project root."""
    return root / _PROJECT_CONFIG_DIR / _SETTINGS_FILE_NAME


def settings_directory(scope: str, root: Path) -> Path:
    """Return the directory relative package sources are resolved against."""
    if scope == INSTALL_SCOPE_USER:
        return pi_agent_dir()
    if scope == INSTALL_SCOPE_PROJECT:
        return root / _PROJECT_CONFIG_DIR
    raise ValueError(f"unsupported Pi scope: {scope}")


def settings_path(scope: str, root: Path) -> Path:
    """Select native settings for exactly one explicit scope."""
    if scope == INSTALL_SCOPE_USER:
        return user_settings_path()
    if scope == INSTALL_SCOPE_PROJECT:
        return project_settings_path(root)
    raise ValueError(f"unsupported Pi scope: {scope}")


def resolve_source(directory: Path, source: str) -> Path:
    """Resolve a settings source relative to Pi's settings directory."""
    candidate = Path(source).expanduser()
    if not candidate.is_absolute():
        candidate = directory / candidate
    return candidate.resolve()


def _settings_object(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        parsed = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise LegacyRefusal(
            f"Refusing malformed Pi settings file: {path}: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise LegacyRefusal(
            f"Refusing malformed Pi settings file (expected object): {path}"
        )
    return cast(dict[str, object], parsed)


def _entry_source(raw: object, path: Path) -> tuple[str, bool]:
    if isinstance(raw, str) and raw:
        return raw, False
    if isinstance(raw, dict):
        entry = cast(dict[str, object], raw)
        source = entry.get(SOURCE_KEY)
        if isinstance(source, str) and source:
            return source, any(
                key in entry for key in ("extensions", "skills", "prompts", "themes")
            )
    raise LegacyRefusal(f"Refusing malformed Pi package entry in {path}: {raw!r}")


def package_entries(path: Path, scope: str, root: Path) -> tuple[PackageEntry, ...]:
    """Read and validate package entries from a scope's native settings file."""
    document = _settings_object(path)
    if document is None:
        return ()
    raw_packages = document.get(_PACKAGES_KEY, [])
    if not isinstance(raw_packages, list):
        raise LegacyRefusal(
            f"Refusing malformed Pi packages setting (expected list): {path}"
        )
    directory = settings_directory(scope, root)
    entries: list[PackageEntry] = []
    for raw in cast(list[object], raw_packages):
        source, filtered = _entry_source(raw, path)
        entries.append(
            PackageEntry(raw, source, resolve_source(directory, source), filtered)
        )
    return tuple(entries)


def registered_entry(scope: str, root: Path, source_root: Path) -> PackageEntry | None:
    """Return the matching local source entry for one scope, if registered."""
    target = source_root.resolve()
    path = settings_path(scope, root)
    for entry in package_entries(path, scope, root):
        if entry.resolved == target:
            return entry
    return None
