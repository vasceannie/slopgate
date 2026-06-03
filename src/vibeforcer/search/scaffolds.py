"""Skill and plugin scaffolding for search integration."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import cast

from vibeforcer._types import ObjectDict, object_dict, object_list
from vibeforcer.search.config import (
    DEFAULT_CLAUDE_SKILLS_DIR,
    DEFAULT_OPENCODE_CONFIG,
    DEFAULT_OPENCODE_PLUGIN_PATH,
    DEFAULT_OPENCODE_SKILLS_DIR,
    DEFAULT_SKILL_NAME,
    IsxError,
)
from vibeforcer.search.opencode_scaffold import render_opencode_plugin


def write_text_file(path: Path, content: str, force: bool) -> None:
    """Write *content* to *path*, erroring if it exists and *force* is False."""
    if path.exists() and not force:
        raise IsxError(f"{path} already exists. Re-run with --force to overwrite it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content)


def append_unique_json_list(path: Path, key: str, value: str) -> None:
    """Append *value* to a JSON array at *key* in *path*."""
    data: ObjectDict
    if path.exists():
        try:
            raw_data = cast(object, json.loads(path.read_text()))
            data = object_dict(raw_data)
        except json.JSONDecodeError as exc:
            raise IsxError(f"could not parse {path} as JSON: {exc}") from exc
    else:
        data = {"$schema": "https://opencode.ai/config.json"}

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
    return textwrap.dedent(
        f"""\
        ---
        name: {skill_name}
        description: Use when the user asks to index repositories, run semantic code search, switch embedding models, or rebuild islands indexes via the local `isx` CLI. Triggers on requests like "search this repo semantically", "index this repo with islands", "switch embedding model", or "reindex after changing models".
        ---

        # {skill_name}

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


def scaffold_opencode_plugin(
    plugin_path: Path = DEFAULT_OPENCODE_PLUGIN_PATH,
    opencode_config: Path = DEFAULT_OPENCODE_CONFIG,
    force: bool = False,
) -> Path:
    """Write the OpenCode plugin and register it in opencode.json."""
    write_text_file(plugin_path, render_opencode_plugin(), force=force)
    append_unique_json_list(opencode_config, "plugin", str(plugin_path))
    return plugin_path
