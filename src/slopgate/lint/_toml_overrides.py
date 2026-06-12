"""Apply slopgate.toml overrides to lint quality config."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from slopgate.config._coerce import object_dict, string_list
from slopgate.config._io import load_toml
from slopgate.policy_defaults import LINT_PATH_DEFAULTS


def _paths_section(project_root: Path) -> dict[str, object]:
    raw_toml = load_toml(project_root)
    paths = raw_toml.get("paths")
    if not isinstance(paths, dict):
        return {}
    return object_dict(cast(dict[object, object], paths))


def _coerce_path_entries(value: object, *, default: str) -> list[str]:
    if value is None:
        return [default]
    if isinstance(value, str):
        trimmed = value.strip()
        return [trimmed] if trimmed else [default]
    if isinstance(value, list):
        entries = [
            str(item).strip() for item in cast(list[object], value) if str(item).strip()
        ]
        return entries if entries else [default]
    text = str(value).strip()
    return [text] if text else [default]


def _resolve_path_entries(project_root: Path, entries: list[str]) -> tuple[Path, ...]:
    resolved: list[Path] = []
    for entry in entries:
        candidate = Path(entry)
        if candidate.is_absolute():
            resolved.append(candidate.resolve())
        else:
            resolved.append((project_root / candidate).resolve())
    return tuple(resolved)


def resolve_root_paths(project_root: Path, key: str, default: str) -> tuple[Path, ...]:
    """Return configured roots from ``[paths].<key>`` (string or array of strings)."""
    paths = _paths_section(project_root)
    entries = _coerce_path_entries(paths.get(key), default=default)
    return _resolve_path_entries(project_root, entries)


def resolve_baseline_path(project_root: Path) -> Path | None:
    """Return configured baseline path from ``[paths].baseline_path``, if set."""
    paths = _paths_section(project_root)
    raw_value = paths.get("baseline_path")
    if not isinstance(raw_value, str):
        return None
    trimmed = raw_value.strip()
    if not trimmed:
        return None
    candidate = Path(trimmed)
    if candidate.is_absolute():
        return candidate.resolve()
    return (project_root / candidate).resolve()


def apply_paths_overrides(values: dict[str, object], project_root: Path) -> None:
    """Merge ``[paths]`` and ``[scope]`` from slopgate.toml into lint config values."""
    src_roots = resolve_root_paths(project_root, "src", LINT_PATH_DEFAULTS["src"])
    test_roots = resolve_root_paths(project_root, "tests", LINT_PATH_DEFAULTS["tests"])
    values["src_roots"] = src_roots
    values["test_roots"] = test_roots
    values["src_root"] = src_roots[0]
    values["tests_root"] = test_roots[0]

    paths = _paths_section(project_root)
    if "exclude_dirs" in paths:
        values["exclude_dirs"] = {item for item in string_list(paths["exclude_dirs"])}
    if "exclude_patterns" in paths:
        values["exclude_patterns"] = [
            item for item in string_list(paths["exclude_patterns"])
        ]

    raw_toml = load_toml(project_root)
    scope = raw_toml.get("scope")
    if isinstance(scope, dict):
        scope_data = object_dict(cast(dict[object, object], scope))
        default_scope = scope_data.get("default")
        if isinstance(default_scope, str) and default_scope.strip():
            values["default_scope"] = default_scope.strip()
        git_base_debt = scope_data.get("git_base_debt")
        if isinstance(git_base_debt, bool):
            values["enable_git_base_debt"] = git_base_debt
