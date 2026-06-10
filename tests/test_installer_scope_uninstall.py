"""Uninstall-scope regression: owned hooks removed, third-party hooks preserved."""

from __future__ import annotations
import json
from pathlib import Path
from collections.abc import Callable
from typing import cast
import pytest
import slopgate.installer._claude
import slopgate.installer._codex
import slopgate.installer._cursor
import slopgate.installer._opencode
import slopgate.installer._shared
from slopgate._types import (
    ObjectDict,
    is_object_dict,
    object_dict,
    object_list,
    string_value,
)
from slopgate.installer._shared import command_is_slopgate_hook


def _third_party_shell_hook(command: str = "./existing.sh") -> dict[str, object]:
    return {"command": command}


def _as_object_dict(value: object) -> ObjectDict | None:
    return value if is_object_dict(value) else None


def _hook_command(entry: ObjectDict) -> str | None:
    return string_value(entry.get("command"))


def _nested_hooks(entry: ObjectDict) -> list[ObjectDict]:
    nested = object_list(entry.get("hooks"))
    hooks: list[ObjectDict] = []
    for item in nested:
        if is_object_dict(item):
            hooks.append(item)
    return hooks


def _claude_read_third_party(parsed: ObjectDict) -> bool:
    hooks = object_dict(parsed.get("hooks"))
    pretool = object_list(hooks.get("PreToolUse"))
    if not pretool:
        return False
    entry = _as_object_dict(pretool[0])
    if entry is None:
        return False
    return any(
        (_hook_command(hook) == "./existing.sh" for hook in _nested_hooks(entry))
    )


def _shell_read_third_party(parsed: ObjectDict) -> bool:
    hooks = object_dict(parsed.get("hooks"))
    shell = object_list(hooks.get("beforeShellExecution"))
    entry = _as_object_dict(shell[0]) if shell else None
    return entry is not None and _hook_command(entry) == "./existing.sh"


def _install_uninstall_project_roundtrip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    install: object,
    uninstall: object,
    config_path: Path,
    read_third_party: object,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.name == "hooks.json":
        config_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "hooks": {"beforeShellExecution": [_third_party_shell_hook()]},
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
                            {"hooks": [{"type": "command", "command": "./existing.sh"}]}
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
    install_fn = cast(Callable[..., int], install)
    uninstall_fn = cast(Callable[..., int], uninstall)
    read_third_party_fn = cast(Callable[[ObjectDict], bool], read_third_party)
    assert install_fn(dry_run=False, scope="project") == 0
    assert uninstall_fn(dry_run=False, scope="project") == 0
    if not config_path.exists():
        return
    parsed = object_dict(json.loads(config_path.read_text(encoding="utf-8")))
    assert read_third_party_fn(parsed)
    hooks = object_dict(parsed.get("hooks"))
    for entries in hooks.values():
        entry_list = object_list(entries)
        for raw_entry in entry_list:
            entry = _as_object_dict(raw_entry)
            if entry is None:
                continue
            command = _hook_command(entry)
            if command_is_slopgate_hook(command):
                raise AssertionError(f"slopgate hook left behind: {command}")
            for hook in _nested_hooks(entry):
                nested_command = _hook_command(hook)
                if command_is_slopgate_hook(nested_command):
                    raise AssertionError(f"slopgate hook left behind: {nested_command}")


def test_claude_project_uninstall_preserves_third_party_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    config_path = tmp_path / ".claude" / "settings.json"
    _install_uninstall_project_roundtrip(
        tmp_path,
        monkeypatch,
        install=slopgate.installer._claude.install_claude,
        uninstall=slopgate.installer._claude.uninstall_claude,
        config_path=config_path,
        read_third_party=_claude_read_third_party,
    )
    nested = json.loads(config_path.read_text(encoding="utf-8"))["hooks"]["PreToolUse"][
        0
    ]["hooks"]
    assert nested[0]["command"] == "./existing.sh"


def test_codex_project_uninstall_preserves_third_party_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    config_path = tmp_path / ".codex" / "hooks.json"
    _install_uninstall_project_roundtrip(
        tmp_path,
        monkeypatch,
        install=slopgate.installer._codex.install_codex,
        uninstall=slopgate.installer._codex.uninstall_codex,
        config_path=config_path,
        read_third_party=_shell_read_third_party,
    )
    shell_entry = json.loads(config_path.read_text(encoding="utf-8"))["hooks"][
        "beforeShellExecution"
    ][0]
    assert shell_entry["command"] == "./existing.sh"


def test_cursor_project_uninstall_preserves_third_party_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    config_path = tmp_path / ".cursor" / "hooks.json"
    _install_uninstall_project_roundtrip(
        tmp_path,
        monkeypatch,
        install=slopgate.installer._cursor.install_cursor,
        uninstall=slopgate.installer._cursor.uninstall_cursor,
        config_path=config_path,
        read_third_party=_shell_read_third_party,
    )
    shell_entry = json.loads(config_path.read_text(encoding="utf-8"))["hooks"][
        "beforeShellExecution"
    ][0]
    assert shell_entry["command"] == "./existing.sh"


def test_opencode_project_uninstall_removes_owned_plugin_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    monkeypatch.chdir(tmp_path)
    assert (
        slopgate.installer._opencode.install_opencode(dry_run=False, scope="project")
        == 0
    )
    plugin_path = tmp_path / ".opencode" / "plugins" / "slopgate-plugin.ts"
    assert plugin_path.exists()
    assert (
        slopgate.installer._opencode.uninstall_opencode(dry_run=False, scope="project")
        == 0
    )
    assert not plugin_path.exists()


def test_uninstall_user_scope_warns_when_project_hooks_remain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(repo)
    assert (
        slopgate.installer._cursor.install_cursor(dry_run=False, scope="project") == 0
    )
    assert slopgate.installer._cursor.uninstall_cursor(dry_run=False, scope="user") == 0
    captured = capsys.readouterr()
    assert "remain at" in captured.out
    assert ".cursor/hooks.json" in captured.out.replace("\\", "/")


def _user_scope_uninstall_leaves_project_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, bool]:
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(repo)
    if slopgate.installer._cursor.install_cursor(dry_run=False, scope="both") != 0:
        raise AssertionError("project+user install failed")
    project_hooks = tmp_path / "repo" / ".cursor" / "hooks.json"
    user_hooks = tmp_path / "home" / ".cursor" / "hooks.json"
    if not project_hooks.exists() or not user_hooks.exists():
        raise AssertionError("expected both hook files to exist")
    if slopgate.installer._cursor.uninstall_cursor(dry_run=False, scope="user") != 0:
        raise AssertionError("user-scope uninstall failed")
    user_parsed = object_dict(json.loads(user_hooks.read_text(encoding="utf-8")))
    project_parsed = object_dict(json.loads(project_hooks.read_text(encoding="utf-8")))
    user_commands = [
        command
        for entries in object_dict(user_parsed.get("hooks")).values()
        for raw_entry in object_list(entries)
        for entry in (_as_object_dict(raw_entry),)
        if entry is not None
        for command in (_hook_command(entry),)
    ]
    project_commands = [
        command
        for entries in object_dict(project_parsed.get("hooks")).values()
        for raw_entry in object_list(entries)
        for entry in (_as_object_dict(raw_entry),)
        if entry is not None
        for command in (_hook_command(entry),)
    ]
    return {
        "user_clean": not any(
            (command_is_slopgate_hook(command) for command in user_commands)
        ),
        "project_retained": any(
            (command_is_slopgate_hook(command) for command in project_commands)
        ),
    }


def test_user_scope_uninstall_does_not_touch_project_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _user_scope_uninstall_leaves_project_hooks(tmp_path, monkeypatch) == {
        "user_clean": True,
        "project_retained": True,
    }
