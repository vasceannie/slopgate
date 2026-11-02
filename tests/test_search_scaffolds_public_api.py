from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, strategies
import pytest

from slopgate.search import scaffolds
from slopgate.search.scaffolds import (
    append_unique_json_list,
    render_isx_skill,
    render_opencode_plugin,
    scaffold_opencode_plugin,
    scaffold_skill,
    write_text_file,
)

SKILL_NAMES = strategies.from_regex(r"[a-z][a-z0-9_-]{0,24}", fullmatch=True)


def test_write_text_file_respects_force_flag(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "file.txt"

    write_text_file(target, "first", force=False)
    with pytest.raises(scaffolds.IsxError, match="already exists"):
        write_text_file(target, "second", force=False)
    write_text_file(target, "second", force=True)

    assert target.read_text(encoding="utf-8") == "second"


def test_append_unique_json_list_creates_and_deduplicates_values(
    tmp_path: Path,
) -> None:
    config = tmp_path / "opencode.json"

    append_unique_json_list(config, "plugins", "/tmp/isx-tools")
    append_unique_json_list(config, "plugins", "/tmp/isx-tools")

    assert json.loads(config.read_text(encoding="utf-8")) == {
        "$schema": "https://opencode.ai/config.json",
        "plugins": ["/tmp/isx-tools"],
    }


def test_renderers_include_expected_commands_and_tool_names() -> None:
    skill = render_isx_skill("isx-cli")
    plugin = render_opencode_plugin()

    assert {
        "skill_name": "# isx-cli" in skill,
        "skill_reindex": "isx reindex <repo-or-index>" in skill,
        "plugin_tool": "isx_search" in plugin,
        "plugin_config": "ISX_CONFIG" in plugin,
    } == {
        "skill_name": True,
        "skill_reindex": True,
        "plugin_tool": True,
        "plugin_config": True,
    }


def test_scaffold_opencode_plugin_writes_plugin_and_registers_config(
    tmp_path: Path,
) -> None:
    legacy_plugin_path = tmp_path / "plugins" / "isx-tools.ts"
    plugin_path = tmp_path / "plugins" / "isx-tools" / "index.ts"
    config_path = tmp_path / "opencode.json"

    result = scaffold_opencode_plugin(legacy_plugin_path, config_path)

    assert {
        "result": result,
        "plugin_content": plugin_path.read_text(encoding="utf-8"),
        "config": json.loads(config_path.read_text(encoding="utf-8")),
    } == {
        "result": plugin_path,
        "plugin_content": render_opencode_plugin(),
        "config": {
            "$schema": "https://opencode.ai/config.json",
            "plugins": [str(plugin_path.parent)],
        },
    }


_LEGACY_V1_ISX_PLUGIN = """import type { Plugin } from "@opencode-ai/plugin"
export const IsxToolsPlugin: Plugin = async () => ({ tool: { isx_doctor: {} } })
"""


def _scaffold_over_legacy_install(
    tmp_path: Path, extra_entries: tuple[str, ...]
) -> tuple[Path, dict[str, object]]:
    legacy = tmp_path / "plugins" / "isx-tools.ts"
    legacy.parent.mkdir()
    legacy.write_text(_LEGACY_V1_ISX_PLUGIN, encoding="utf-8")
    config = tmp_path / "opencode.json"
    config.write_text(
        json.dumps({"plugin": [str(legacy), *extra_entries]}), encoding="utf-8"
    )
    scaffold_opencode_plugin(tmp_path / "plugins" / "isx-tools" / "index.ts", config)
    return legacy, json.loads(config.read_text(encoding="utf-8"))


def test_scaffold_backs_up_and_removes_owned_legacy_plugin(tmp_path: Path) -> None:
    legacy, _config = _scaffold_over_legacy_install(tmp_path, ())

    assert not legacy.exists(), "a V1 file would keep failing to load under V2"
    assert list(legacy.parent.glob("isx-tools.ts.slopgate-bak-*")), (
        "the removed legacy plugin must stay recoverable from a backup"
    )


def test_scaffold_keeps_other_legacy_config_entries(tmp_path: Path) -> None:
    _legacy, config = _scaffold_over_legacy_install(tmp_path, ("other",))

    assert config["plugin"] == ["other"], (
        "only the owned legacy entry may be removed from the V1 config key"
    )


def test_scaffold_drops_empty_legacy_plugin_key(tmp_path: Path) -> None:
    _legacy, config = _scaffold_over_legacy_install(tmp_path, ())

    assert "plugin" not in config, "an empty V1 key should not linger in a V2 config"


def test_scaffold_keeps_unrecognized_file_at_legacy_path(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins" / "isx-tools"
    unrelated = tmp_path / "plugins" / "isx-tools.ts"
    unrelated.parent.mkdir()
    unrelated.write_text("export const Mine = 1\n", encoding="utf-8")

    scaffold_opencode_plugin(plugin_dir / "index.ts", tmp_path / "opencode.json")

    assert unrelated.read_text(encoding="utf-8") == "export const Mine = 1\n", (
        "files slopgate did not write must not be removed"
    )


def test_scaffold_skill_writes_requested_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claude_dir = tmp_path / "claude"
    opencode_dir = tmp_path / "opencode"
    monkeypatch.setattr(scaffolds, "DEFAULT_CLAUDE_SKILLS_DIR", claude_dir)
    monkeypatch.setattr(scaffolds, "DEFAULT_OPENCODE_SKILLS_DIR", opencode_dir)

    destinations = scaffold_skill("isx-cli", skill_target="both")

    assert {
        "destinations": destinations,
        "claude_exists": (claude_dir / "isx-cli" / "SKILL.md").exists(),
        "opencode_exists": (opencode_dir / "isx-cli" / "SKILL.md").exists(),
    } == {
        "destinations": [
            claude_dir / "isx-cli" / "SKILL.md",
            opencode_dir / "isx-cli" / "SKILL.md",
        ],
        "claude_exists": True,
        "opencode_exists": True,
    }


@given(SKILL_NAMES)
def test_render_isx_skill_includes_requested_skill_name_property(
    skill_name: str,
) -> None:
    rendered = render_isx_skill(skill_name)

    assert f"name: {skill_name}" in rendered


@given(SKILL_NAMES)
def test_append_unique_json_list_preserves_single_value_property(value: str) -> None:
    with TemporaryDirectory() as raw_path:
        config = Path(raw_path) / "opencode.json"
        append_unique_json_list(config, "plugins", value)
        append_unique_json_list(config, "plugins", value)
        data = json.loads(config.read_text(encoding="utf-8"))

    assert data["plugins"] == [value]
