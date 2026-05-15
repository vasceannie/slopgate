from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import tomli

import vibeforcer.installer as installer_module


def _hook_builder(name: str) -> Any:
    return getattr(installer_module, name)


def test_codex_hooks_cover_current_tool_events() -> None:
    hooks = _hook_builder("_codex_hooks_block")("vibeforcer")
    pre = hooks["PreToolUse"][0]
    post = hooks["PostToolUse"][0]
    permission = hooks["PermissionRequest"][0]
    pre_matcher = str(pre.get("matcher", ""))
    post_matcher = str(post.get("matcher", ""))
    permission_matcher = str(permission.get("matcher", ""))
    for matcher in (pre_matcher, post_matcher, permission_matcher):
        assert "Bash" in matcher
        assert "apply_patch" in matcher
        assert "Edit" in matcher
        assert "Write" in matcher


def test_codex_installer_enables_current_toml_feature(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '\n'.join(
            [
                'model = "gpt-5"',
                '',
                '[features]',
                'plugin_hooks = true',
                'codex_hooks = false # stale',
                '',
                '[projects."/tmp/example"]',
                'trust_level = "trusted"',
                '',
            ]
        ),
        encoding="utf-8",
    )

    installer_module._enable_codex_hooks_toml(config_path)

    parsed = tomli.loads(config_path.read_text(encoding="utf-8"))
    assert parsed["features"]["codex_hooks"] is True
    assert parsed["features"]["plugin_hooks"] is True
    assert parsed["projects"]["/tmp/example"]["trust_level"] == "trusted"


def test_codex_installer_creates_toml_features_section(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"

    installer_module._enable_codex_hooks_toml(config_path)

    parsed = tomli.loads(config_path.read_text(encoding="utf-8"))
    assert parsed["features"]["codex_hooks"] is True


def test_codex_install_writes_hooks_and_toml_feature(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(installer_module, "_find_binary", lambda: "vibeforcer")

    assert installer_module._install_codex(dry_run=False) == 0

    hooks = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
    config = tomli.loads((tmp_path / ".codex" / "config.toml").read_text())
    assert "PermissionRequest" in hooks["hooks"]
    assert config["features"]["codex_hooks"] is True


def test_claude_install_preserves_unrelated_hooks_and_replaces_only_vibeforcer(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(installer_module, "_find_binary", lambda: "vibeforcer")
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {"type": "command", "command": "other-gate"}
                            ],
                        },
                        {
                            "hooks": [
                                {"type": "command", "command": "old-vibeforcer handle"}
                            ],
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    assert installer_module._install_claude(dry_run=False) == 0

    hooks = json.loads(settings_path.read_text(encoding="utf-8"))["hooks"]
    commands = [
        hook["command"]
        for entry in hooks["PreToolUse"]
        for hook in entry.get("hooks", [])
    ]
    assert "other-gate" in commands
    assert "old-vibeforcer handle" not in commands
    assert commands.count("vibeforcer handle") == 1


def test_claude_uninstall_removes_only_vibeforcer_hooks(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {"type": "command", "command": "other-gate"}
                            ],
                        },
                        {
                            "hooks": [
                                {"type": "command", "command": "vibeforcer handle"}
                            ],
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    assert installer_module._uninstall_claude(dry_run=False) == 0

    hooks = json.loads(settings_path.read_text(encoding="utf-8"))["hooks"]
    commands = [
        hook["command"]
        for entry in hooks["PreToolUse"]
        for hook in entry.get("hooks", [])
    ]
    assert commands == ["other-gate"]


def test_codex_install_preserves_unrelated_hooks_and_replaces_only_vibeforcer(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(installer_module, "_find_binary", lambda: "vibeforcer")
    hooks_path = tmp_path / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {"type": "command", "command": "other-gate"}
                            ],
                        },
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "old-vibeforcer handle --platform codex",
                                }
                            ],
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    assert installer_module._install_codex(dry_run=False) == 0

    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))["hooks"]
    commands = [
        hook["command"]
        for entry in hooks["PreToolUse"]
        for hook in entry.get("hooks", [])
    ]
    assert "other-gate" in commands
    assert "old-vibeforcer handle --platform codex" not in commands
    assert commands.count("vibeforcer handle --platform codex") == 1


def test_claude_hooks_include_cwd_changed() -> None:
    hooks = _hook_builder("_claude_hooks_block")("vibeforcer")
    assert "CwdChanged" in hooks


def test_opencode_plugin_treats_empty_success_as_allow_noop() -> None:
    from vibeforcer.resources import resource_path

    plugin = resource_path("opencode_plugin.ts").read_text(encoding="utf-8")
    assert "empty enforcer response" not in plugin
    assert "if (!trimmed) return null" in plugin
    assert "exits 0 with no stdout" in plugin


def test_opencode_plugin_caches_pretool_args_for_posttool_backstops() -> None:
    from vibeforcer.resources import resource_path

    plugin = resource_path("opencode_plugin.ts").read_text(encoding="utf-8")
    assert "const postToolArgCache: ToolArgsCacheEntry[] = []" in plugin
    assert "function rememberToolArgs(" in plugin
    assert "function takeRememberedToolArgs(" in plugin
    assert "tool_input: preToolArgs" in plugin
    assert "rememberToolArgs(input.tool, currentDirectory, preToolArgs)" in plugin
    assert "const rememberedArgs = takeRememberedToolArgs(input.tool, currentDirectory)" in plugin
    assert "const postToolArgs = { ...rememberedArgs, ...cloneArgs(output.args) }" in plugin
    assert "tool_input: postToolArgs" in plugin


def test_opencode_plugin_cache_is_bounded_ttl_scoped_and_consumed() -> None:
    from vibeforcer.resources import resource_path

    plugin = resource_path("opencode_plugin.ts").read_text(encoding="utf-8")
    assert "POST_TOOL_ARG_CACHE_TTL_MS = 5 * 60 * 1000" in plugin
    assert "POST_TOOL_ARG_CACHE_MAX_ENTRIES = 50" in plugin
    assert "entry.tool === toolName && entry.cwd === cwd" in plugin
    assert "postToolArgCache.splice(index, 1)" in plugin
