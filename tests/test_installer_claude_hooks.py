"""Claude installer hook tests split from test_installer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pytest import CaptureFixture, MonkeyPatch

import vibeforcer.installer as installer_module
import vibeforcer.installer._shared as installer_shared
import vibeforcer.util.platform as platform_utils

from tests.test_installer import (
    _all_hook_commands,
    _dry_run_install_json,
    _existing_claude_settings,
    _existing_codex_hooks,
    _hook_builder,
    _hook_commands,
    _install_with_existing_hooks,
    _installed_hook_commands,
)


def test_claude_install_preserves_unrelated_hooks_and_replaces_only_vibeforcer(
    tmp_path: Path, monkeypatch: Any
) -> None:
    settings_path = _install_with_existing_hooks(
        tmp_path,
        monkeypatch,
        ".claude",
        "settings.json",
        _existing_claude_settings(),
    )

    assert installer_module._install_claude(dry_run=False) == 0

    commands = _installed_hook_commands(settings_path)
    assert "other-gate" in commands
    assert "/old/bin/vibeforcer handle" not in commands
    assert commands.count("vibeforcer handle") == 1


def test_claude_install_preserves_unrelated_hook_inside_mixed_entry(
    tmp_path: Path, monkeypatch: Any
) -> None:
    settings_path = _install_with_existing_hooks(
        tmp_path,
        monkeypatch,
        ".claude",
        "settings.json",
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": "other-gate"},
                            {"type": "command", "command": "vibeforcer handle"},
                        ],
                    }
                ]
            }
        },
    )

    assert installer_module._install_claude(dry_run=False) == 0

    commands = _installed_hook_commands(settings_path)
    assert "other-gate" in commands
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


def test_claude_uninstall_preserves_unrelated_hook_inside_mixed_entry(
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
                                {"type": "command", "command": "other-gate"},
                                {"type": "command", "command": "vibeforcer handle"},
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    assert installer_module._uninstall_claude(dry_run=False) == 0

    hooks = json.loads(settings_path.read_text(encoding="utf-8"))["hooks"]
    commands = _hook_commands(hooks)
    assert commands == ["other-gate"]


def test_claude_uninstall_preserves_user_hook_that_only_mentions_vibeforcer_handle(
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
                                {
                                    "type": "command",
                                    "command": "printf 'docs mention vibeforcer handle only'",
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    assert installer_module._uninstall_claude(dry_run=False) == 0

    hooks = json.loads(settings_path.read_text(encoding="utf-8"))["hooks"]
    assert _hook_commands(hooks) == ["printf 'docs mention vibeforcer handle only'"]


def test_codex_install_preserves_unrelated_hooks_and_replaces_only_vibeforcer(
    tmp_path: Path, monkeypatch: Any
) -> None:
    hooks_path = _install_with_existing_hooks(
        tmp_path,
        monkeypatch,
        ".codex",
        "hooks.json",
        _existing_codex_hooks(),
    )

    assert installer_module._install_codex(dry_run=False) == 0

    commands = _installed_hook_commands(hooks_path)
    assert "other-gate" in commands
    assert "/old/bin/vibeforcer handle --platform codex" not in commands
    assert commands.count("vibeforcer handle --platform codex") == 1


def test_codex_uninstall_preserves_non_hook_user_settings_when_only_owned_hooks_remain(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    hooks_path = tmp_path / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(
        json.dumps(
            {
                "customSetting": {"keep": True},
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "vibeforcer handle --platform codex",
                                }
                            ],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    assert installer_module._uninstall_codex(dry_run=False) == 0

    remaining = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert remaining == {"customSetting": {"keep": True}}
    assert sorted(hooks_path.parent.glob("hooks.json.vibeforcer-bak-*"))


def test_claude_hooks_include_cwd_changed() -> None:
    hooks = _hook_builder("_claude_hooks_block")("vibeforcer")
    assert "CwdChanged" in hooks


def test_claude_dry_run_hooks_include_cwd_changed(
    capsys: CaptureFixture[str], monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    data = _dry_run_install_json("claude", capsys, monkeypatch, tmp_path)
    assert "CwdChanged" in data["hooks"]


def test_windows_codex_install_emits_powershell_hook_commands(
    capsys: CaptureFixture[str], monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    data = _dry_run_install_json(
        "codex",
        capsys,
        monkeypatch,
        tmp_path,
        binary=r"C:\Users\Trav App\AppData\Local\Programs\Python\Scripts\vibeforcer.exe",
        windows=True,
    )
    commands = list(_all_hook_commands(data["hooks"]))
    assert commands
    command_contracts = [
        (
            command.startswith("powershell.exe "),
            "-NoProfile" in command,
            "-NonInteractive" in command,
            "-Command" in command,
            "C:\\Users\\Trav App\\AppData" in command,
            "handle" in command,
            "codex" in command,
        )
        for command in commands
    ]
    assert command_contracts == [(True, True, True, True, True, True, True)] * len(commands)


def test_claude_install_falls_back_to_python_module_invocation(
    capsys: CaptureFixture[str], monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    data = _dry_run_install_json(
        "claude",
        capsys,
        monkeypatch,
        tmp_path,
        binary=None,
    )
    commands = list(_all_hook_commands(data["hooks"]))
    assert commands
    assert all(" -m vibeforcer handle" in command for command in commands)


def test_opencode_install_bakes_windows_binary_into_plugin(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    binary = r"C:\Users\Trav App\AppData\Local\Programs\Python\Scripts\vibeforcer.exe"

    def which(name: str) -> str | None:
        return binary if name == "vibeforcer" else None

    monkeypatch.setattr(platform_utils, "is_windows", lambda: True)
    monkeypatch.setattr(installer_shared.shutil, "which", which)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))

    assert installer_module.install_platform("opencode", dry_run=False) == 0

    plugin_path = tmp_path / "Roaming" / "opencode" / "plugins" / "vibeforcer-plugin.ts"
    plugin = plugin_path.read_text(encoding="utf-8")
    assert "__VIBEFORCER_BIN__" not in plugin
    assert json.dumps(binary) in plugin
    assert "Bun.env.VIBEFORCER_BIN ||" in plugin


def test_opencode_plugin_treats_empty_success_as_allow_noop() -> None:
    from vibeforcer.resources import resource_path

    plugin = resource_path("opencode_plugin.ts").read_text(encoding="utf-8")
    assert "empty enforcer response" not in plugin
    assert "if (!trimmed) return null" in plugin
    assert "exits 0 with no stdout" in plugin
