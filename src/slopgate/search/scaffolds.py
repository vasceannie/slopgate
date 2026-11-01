"""Skill and plugin scaffolding for search integration."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import cast

from slopgate._types import ObjectDict, object_dict, object_list
from slopgate.constants import REPLACE
from slopgate.installer._shared import remove_file_with_backup
from slopgate.search.config import (
    DEFAULT_CLAUDE_SKILLS_DIR,
    DEFAULT_OPENCODE_CONFIG,
    DEFAULT_OPENCODE_PLUGIN_PATH,
    DEFAULT_OPENCODE_SKILLS_DIR,
    DEFAULT_SKILL_NAME,
    IsxError,
)
from slopgate.search.opencode_scaffold import render_opencode_plugin

_LEGACY_PLUGIN_CONFIG_KEY = "plugin"
_LEGACY_ISX_PLUGIN_MARKERS = ("@opencode-ai/plugin", "IsxToolsPlugin")
_ISX_SKILL_DESCRIPTION = (
    "Use when the user asks to index repositories, run semantic code search, "
    "switch embedding models, or rebuild islands indexes via the local `isx` CLI. "
    'Triggers on requests like "search this repo semantically", '
    '"index this repo with islands", "switch embedding model", '
    'or "reindex after changing models".'
)
_ISX_SKILL_BODY = textwrap.dedent(
    """\
    Use the local `isx` CLI instead of reconstructing islands commands by hand.

    ## Workflow

    1. Run `isx doctor` if the runtime may not be configured yet.
    2. Use `isx list` to see known indexes.
    3. Use `isx add <repo-url>` to index a repository.
    4. Use `isx search "query"` for semantic search.
    5. Use `isx models` and `isx use <model>` when changing embedding routes.
    6. After changing to a model with a different embedding dimension, run `isx reindex <repo-or-index>` before searching again.

    ## Notes

    - Prefer `isx` over raw `islands-ollama` unless you specifically need upstream-only flags.
    - `isx` already injects the configured OpenAI-compatible base URL and API key.
    - `isx reindex` is the safe recovery path after model changes.
    """
)


def write_text_file(path: Path, content: str, force: bool) -> None:
    """Write *content* to *path*, erroring if it exists and *force* is False."""
    if path.exists() and not force:
        raise IsxError(f"{path} already exists. Re-run with --force to overwrite it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content)


def _read_json_config(path: Path) -> ObjectDict:
    try:
        return object_dict(cast(object, json.loads(path.read_text())))
    except json.JSONDecodeError as exc:
        raise IsxError(f"could not parse {path} as JSON: {exc}") from exc


def append_unique_json_list(path: Path, key: str, value: str) -> None:
    """Append *value* to a JSON array at *key* in *path*."""
    data: ObjectDict = (
        _read_json_config(path)
        if path.exists()
        else {"$schema": "https://opencode.ai/config.json"}
    )

    items = object_list(data.get(key))
    if data.get(key) is not None and not items:
        raise IsxError(f"expected {path}:{key} to be a JSON array")
    if value not in items:
        items.append(value)
    data[key] = items

    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(data, indent=2) + "\n")


def render_isx_skill(skill_name: str) -> str:
    """Render the SKILL.md content for the isx skill."""
    header = (
        f"---\nname: {skill_name}\ndescription: {_ISX_SKILL_DESCRIPTION}\n---\n\n"
        f"# {skill_name}\n\n"
    )
    return header + _ISX_SKILL_BODY


def scaffold_skill(
    skill_name: str = DEFAULT_SKILL_NAME,
    skill_target: str = "both",
    force: bool = False,
) -> list[Path]:
    """Write the isx SKILL.md to one or more skill directories."""
    destinations: list[Path] = []
    if skill_target in {"claude", "both"}:
        destinations.append(DEFAULT_CLAUDE_SKILLS_DIR / skill_name / "SKILL.md")
    if skill_target in {"opencode", "both"}:
        destinations.append(DEFAULT_OPENCODE_SKILLS_DIR / skill_name / "SKILL.md")

    content = render_isx_skill(skill_name)
    for path in destinations:
        write_text_file(path, content, force=force)
    return destinations


def _opencode_plugin_paths(plugin_path: Path) -> tuple[Path, Path]:
    """Return the source file and directory for a V2 OpenCode plugin."""
    if plugin_path.name == "index.ts":
        return plugin_path, plugin_path.parent
    if plugin_path.suffix:
        plugin_dir = plugin_path.parent / plugin_path.stem
        return plugin_dir / "index.ts", plugin_dir
    return plugin_path / "index.ts", plugin_path


def _remove_legacy_config_entry(config: Path, value: str) -> None:
    if not config.exists():
        return
    data = _read_json_config(config)
    legacy_entries = object_list(data.get(_LEGACY_PLUGIN_CONFIG_KEY))
    if value not in legacy_entries:
        return
    remaining = [item for item in legacy_entries if item != value]
    if remaining:
        data[_LEGACY_PLUGIN_CONFIG_KEY] = remaining
    else:
        del data[_LEGACY_PLUGIN_CONFIG_KEY]
    _ = config.write_text(json.dumps(data, indent=2) + "\n")


def _remove_legacy_isx_plugin(plugin_dir: Path, config: Path) -> None:
    """Retire the single-file V1 plugin that a V2 host fails to load."""
    legacy = plugin_dir.parent / f"{plugin_dir.name}.ts"
    if legacy.is_file():
        content = legacy.read_text(encoding="utf-8", errors=REPLACE)
        if not all(marker in content for marker in _LEGACY_ISX_PLUGIN_MARKERS):
            return
        remove_file_with_backup(legacy, "legacy plugin")
    _remove_legacy_config_entry(config, str(legacy))


def scaffold_opencode_plugin(
    plugin_path: Path = DEFAULT_OPENCODE_PLUGIN_PATH,
    opencode_config: Path = DEFAULT_OPENCODE_CONFIG,
    force: bool = False,
) -> Path:
    """Write the OpenCode V2 plugin and register its directory in opencode.json."""
    source_path, plugin_dir = _opencode_plugin_paths(plugin_path)
    write_text_file(source_path, render_opencode_plugin(), force=force)
    _remove_legacy_isx_plugin(plugin_dir, opencode_config)
    append_unique_json_list(opencode_config, "plugins", str(plugin_dir))
    return source_path
