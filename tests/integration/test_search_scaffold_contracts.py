from __future__ import annotations

from pathlib import Path

from slopgate.search.opencode_scaffold import render_opencode_plugin
from slopgate.search.scaffolds import scaffold_opencode_plugin


def test_scaffold_opencode_plugin_writes_rendered_plugin(tmp_path: Path) -> None:
    legacy_plugin_path = tmp_path / "plugins" / "isx-tools.ts"
    plugin_path = tmp_path / "plugins" / "isx-tools" / "index.ts"
    config_path = tmp_path / "opencode.json"

    result = scaffold_opencode_plugin(legacy_plugin_path, config_path)

    assert result == plugin_path, (
        "scaffold_opencode_plugin should return the actual source path"
    )
    assert plugin_path.read_text(encoding="utf-8") == render_opencode_plugin(), (
        "scaffold_opencode_plugin should write the rendered OpenCode plugin source"
    )
