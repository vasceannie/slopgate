"""Uninstall-scope regression: owned hooks removed, third-party hooks preserved."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import slopgate.installer._claude as claude_installer
import slopgate.installer._codex as codex_installer
import slopgate.installer._cursor as cursor_installer
import slopgate.installer._opencode as opencode_installer
from slopgate.installer._opencode import _PLUGIN_OWNERSHIP_MARKERS
from slopgate.installer._shared import command_is_slopgate_hook


def _third_party_shell_hook(command: str = "./existing.sh") -> dict[str, object]:
    return {"command": command}


def _install_uninstall_project_roundtrip(
    tmp_path: Path,
    monkeypatch: Any,
    *,
    install: Callable[..., int],
    uninstall: Callable[..., int],
    config_path: Path,
    read_third_party: Callable[[dict[str, object]], bool],
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.name == "hooks.json":
        config_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "hooks": {
                        "beforeShellExecution": [_third_party_shell_hook()],
                    },
                }
            ),
            encoding="utf-8",
        )
    elif config_path.name == "settings.json":
        config_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "hooks": [
                                    {"type": "command", "command": "./existing.sh"},
                                ]
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )

    assert install(dry_run=False, scope="project") == 0
    assert uninstall(dry_run=False, scope="project") == 0

    if not config_path.exists():
        return

    parsed = json.loads(config_path.read_text(encoding="utf-8"))
    assert read_third_party(parsed)
    hooks = parsed.get("hooks", {})
    if isinstance(hooks, dict):
        for entries in hooks.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict):
                    command = entry.get("command")
                    if command_is_slopgate_hook(command):
                        raise AssertionError(f"slopgate hook left behind: {command}")
                    nested = entry.get("hooks")
                    if isinstance(nested, list):
                        for hook in nested:
                            if isinstance(hook, dict) and command_is_slopgate_hook(
                                hook.get("command")
                            ):
                                raise AssertionError(
                                    f"slopgate hook left behind: {hook['command']}"
                                )


def test_claude_project_uninstall_preserves_third_party_hooks(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(claude_installer, "find_binary", lambda: "/tmp/slopgate")

    def read_third_party(parsed: dict[str, object]) -> bool:
        hooks = parsed.get("hooks")
        if not isinstance(hooks, dict):
            return False
        pretool = hooks.get("PreToolUse")
        if not isinstance(pretool, list) or not pretool:
            return False
        entry = pretool[0]
        if not isinstance(entry, dict):
            return False
        nested = entry.get("hooks")
        if not isinstance(nested, list):
            return False
        return any(
            isinstance(hook, dict) and hook.get("command") == "./existing.sh"
            for hook in nested
        )

    _install_uninstall_project_roundtrip(
        tmp_path,
        monkeypatch,
        install=claude_installer._install_claude,
        uninstall=claude_installer._uninstall_claude,
        config_path=tmp_path / ".claude" / "settings.json",
        read_third_party=read_third_party,
    )


def test_codex_project_uninstall_preserves_third_party_hooks(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(codex_installer, "find_binary", lambda: "/tmp/slopgate")

    def read_third_party(parsed: dict[str, object]) -> bool:
        hooks = parsed.get("hooks")
        if not isinstance(hooks, dict):
            return False
        shell = hooks.get("beforeShellExecution")
        if not isinstance(shell, list) or not shell:
            return False
        entry = shell[0]
        return isinstance(entry, dict) and entry.get("command") == "./existing.sh"

    _install_uninstall_project_roundtrip(
        tmp_path,
        monkeypatch,
        install=codex_installer._install_codex,
        uninstall=codex_installer._uninstall_codex,
        config_path=tmp_path / ".codex" / "hooks.json",
        read_third_party=read_third_party,
    )


def test_cursor_project_uninstall_preserves_third_party_hooks(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(cursor_installer, "find_binary", lambda: "/tmp/slopgate")

    def read_third_party(parsed: dict[str, object]) -> bool:
        hooks = parsed.get("hooks")
        if not isinstance(hooks, dict):
            return False
        shell = hooks.get("beforeShellExecution")
        if not isinstance(shell, list) or not shell:
            return False
        entry = shell[0]
        return isinstance(entry, dict) and entry.get("command") == "./existing.sh"

    _install_uninstall_project_roundtrip(
        tmp_path,
        monkeypatch,
        install=cursor_installer._install_cursor,
        uninstall=cursor_installer._uninstall_cursor,
        config_path=tmp_path / ".cursor" / "hooks.json",
        read_third_party=read_third_party,
    )


def test_opencode_project_uninstall_removes_owned_plugin_only(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(opencode_installer, "find_binary", lambda: "/tmp/slopgate")
    monkeypatch.chdir(tmp_path)

    assert opencode_installer._install_opencode(dry_run=False, scope="project") == 0
    plugin_path = tmp_path / ".opencode" / "plugins" / "slopgate-plugin.ts"
    assert plugin_path.exists()

    assert opencode_installer._uninstall_opencode(dry_run=False, scope="project") == 0
    assert not plugin_path.exists()


def test_uninstall_user_scope_warns_when_project_hooks_remain(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(cursor_installer, "find_binary", lambda: "/tmp/slopgate")
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(repo)

    assert cursor_installer._install_cursor(dry_run=False, scope="project") == 0
    assert cursor_installer._uninstall_cursor(dry_run=False, scope="user") == 0

    captured = capsys.readouterr()
    assert "remain at" in captured.out
    assert ".cursor/hooks.json" in captured.out


def test_user_scope_uninstall_does_not_touch_project_install(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(cursor_installer, "find_binary", lambda: "/tmp/slopgate")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(repo)

    assert cursor_installer._install_cursor(dry_run=False, scope="both") == 0
    project_hooks = tmp_path / "repo" / ".cursor" / "hooks.json"
    user_hooks = tmp_path / "home" / ".cursor" / "hooks.json"
    assert project_hooks.exists() and user_hooks.exists()

    assert cursor_installer._uninstall_cursor(dry_run=False, scope="user") == 0

    user_parsed = json.loads(user_hooks.read_text(encoding="utf-8"))
    project_parsed = json.loads(project_hooks.read_text(encoding="utf-8"))
    user_commands = [
        entry.get("command")
        for entries in user_parsed.get("hooks", {}).values()
        if isinstance(entries, list)
        for entry in entries
        if isinstance(entry, dict)
    ]
    project_commands = [
        entry.get("command")
        for entries in project_parsed.get("hooks", {}).values()
        if isinstance(entries, list)
        for entry in entries
        if isinstance(entry, dict)
    ]
    assert not any(command_is_slopgate_hook(command) for command in user_commands)
    assert any(command_is_slopgate_hook(command) for command in project_commands)
