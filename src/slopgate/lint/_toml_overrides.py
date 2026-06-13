"""Apply slopgate.toml overrides to lint quality config."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from slopgate.config._coerce import object_dict, string_list
from slopgate.config._discovery import resolve_config_path
from slopgate.config._io import load_json, load_toml
from slopgate.lint._parity import (
    HOOK_RULE_BASELINE_COUNTERPARTS,
    classified_collector_keys,
)
from slopgate.policy_defaults import LINT_PATH_DEFAULTS


def _paths_section(project_root: Path) -> dict[str, object]:
    raw_toml = load_toml(project_root)
    paths = raw_toml.get("paths")
    if not isinstance(paths, dict):
        return {}
    return object_dict(cast(dict[object, object], paths))


def _bool_map(value: object) -> dict[str, bool]:
    return {
        key: item for key, item in object_dict(value).items() if isinstance(item, bool)
    }


def _global_enabled_cli_rules() -> dict[str, bool]:
    return _bool_map(load_json(resolve_config_path()).get("enabled_cli_rules", {}))


def _repo_enabled_cli_rules(project_root: Path) -> dict[str, bool]:
    return _bool_map(load_toml(project_root).get("enabled_cli_rules", {}))


def _surface_cli_rules(value: object) -> dict[str, bool]:
    enabled_rules: dict[str, bool] = {}
    collector_keys = classified_collector_keys()
    for rule_id, item in object_dict(value).items():
        cli_enabled = object_dict(object_dict(item).get("cli")).get("enabled")
        if not isinstance(cli_enabled, bool):
            continue
        collector_ids = HOOK_RULE_BASELINE_COUNTERPARTS.get(rule_id, ())
        for collector_id in collector_ids or (rule_id,):
            if collector_id in collector_keys:
                enabled_rules[collector_id] = cli_enabled
    return enabled_rules


def _global_surface_cli_rules() -> dict[str, bool]:
    return _surface_cli_rules(load_json(resolve_config_path()).get("rule_surfaces", {}))


def _repo_surface_cli_rules(project_root: Path) -> dict[str, bool]:
    return _surface_cli_rules(load_toml(project_root).get("rule_surfaces", {}))


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


def apply_rule_enablement_overrides(
    values: dict[str, object], project_root: Path
) -> None:
    enabled_cli_rules = _global_enabled_cli_rules()
    enabled_cli_rules.update(_global_surface_cli_rules())
    enabled_cli_rules.update(_repo_enabled_cli_rules(project_root))
    enabled_cli_rules.update(_repo_surface_cli_rules(project_root))
    values["enabled_cli_rules"] = enabled_cli_rules
