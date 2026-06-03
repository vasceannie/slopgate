from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import vibeforcer.installer as installer_module
import vibeforcer.installer._shared as installer_shared
from vibeforcer.installer._shared import (
    backup_existing_file,
    backup_existing_file_and_report,
    base_invocation,
    coerce_hook_entries,
    find_binary,
    merge_owned_hooks_into,
    require_json_object,
    write_json_with_backup,
)


def _hook_commands(settings_path: Path) -> list[str]:
    hooks = json.loads(settings_path.read_text(encoding="utf-8"))["hooks"]
    return [
        hook["command"]
        for entry in hooks["PreToolUse"]
        for hook in entry.get("hooks", [])
    ]


@pytest.mark.parametrize(
    "command",
    [
        "vibeforcer handle",
        "vibeforcer.exe handle",
        "python -m vibeforcer handle",
    ],
)
def test_command_ownership_recognizes_exact_vibeforcer_invocations(command: str) -> None:
    assert installer_shared.command_is_vibeforcer_hook(command)


def test_command_ownership_recognizes_windows_powershell_hook_command() -> None:
    command = installer_shared.hook_command(
        r"C:\\Tools\\Vibeforcer Bin\\vibeforcer.exe", "handle", windows=True
    )

    assert installer_shared.command_is_vibeforcer_hook(command)


@pytest.mark.parametrize(
    "command",
    [
        "my-vibeforcer-helper handle",
        "/opt/not-vibeforcer handle",
        "vibeforcer-doc handle",
    ],
)
def test_command_ownership_preserves_unrelated_vibeforcer_named_helpers(
    command: str,
) -> None:
    assert not installer_shared.command_is_vibeforcer_hook(command)


def _old_powershell_hook() -> str:
    return installer_shared.hook_command(
        r"C:\\Old Tools\\vibeforcer.exe", "handle", windows=True
    )


def _seed_claude_hook_settings(
    tmp_path: Path,
    monkeypatch: Any,
    first_command: str,
    second_command: str,
) -> Path:
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {"type": "command", "command": first_command},
                                {"type": "command", "command": second_command},
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    return settings_path


def test_claude_reinstall_replaces_powershell_owned_hook_and_preserves_user_hooks(
    tmp_path: Path, monkeypatch: Any
) -> None:
    old_owned = _old_powershell_hook()
    settings_path = _seed_claude_hook_settings(
        tmp_path, monkeypatch, "my-vibeforcer-helper handle", old_owned
    )
    monkeypatch.setattr(installer_module, "_find_binary", lambda: "vibeforcer")

    result = installer_module._install_claude(dry_run=False)

    assert {"result": result, "commands": _hook_commands(settings_path)} == {
        "result": 0,
        "commands": ["my-vibeforcer-helper handle", "vibeforcer handle"],
    }


def test_claude_uninstall_removes_powershell_owned_hook_and_preserves_user_hooks(
    tmp_path: Path, monkeypatch: Any
) -> None:
    settings_path = _seed_claude_hook_settings(
        tmp_path, monkeypatch, "vibeforcer-doc handle", _old_powershell_hook()
    )

    result = installer_module._uninstall_claude(dry_run=False)

    assert {"result": result, "commands": _hook_commands(settings_path)} == {
        "result": 0,
        "commands": ["vibeforcer-doc handle"],
    }


def test_find_binary_returns_string() -> None:
    result = find_binary()

    assert isinstance(result, str)
    assert result != ""


def test_base_invocation_returns_module_args_for_python_executable() -> None:
    import sys

    result = base_invocation(sys.executable)

    assert result == [sys.executable, "-m", "vibeforcer"]


def test_base_invocation_returns_direct_invocation_for_named_binary() -> None:
    result = base_invocation("vibeforcer")

    assert result == ["vibeforcer"]


def test_coerce_hook_entries_filters_non_dicts() -> None:
    raw: list[object] = [{"type": "command", "command": "x"}, "not-a-dict", None, 42]

    result = coerce_hook_entries(raw)

    assert result == [{"type": "command", "command": "x"}]


def test_coerce_hook_entries_returns_empty_for_non_list() -> None:
    assert coerce_hook_entries("not-a-list") == []


def test_require_json_object_parses_valid_json(tmp_path: Path, capsys: Any) -> None:
    config_file = tmp_path / "settings.json"
    config_file.write_text('{"hooks": {}}', encoding="utf-8")

    result = require_json_object(config_file, "settings", action="install")

    assert result == {"hooks": {}}


def test_require_json_object_returns_none_for_invalid_json(tmp_path: Path, capsys: Any) -> None:
    config_file = tmp_path / "bad.json"
    config_file.write_text("not json", encoding="utf-8")

    result = require_json_object(config_file, "settings", action="install")

    assert result is None


def test_merge_owned_hooks_into_replaces_hooks_key(tmp_path: Path) -> None:
    config: dict[str, object] = {"other": "value", "hooks": {}}
    managed: dict[str, list[dict[str, object]]] = {
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "vibeforcer handle"}]}]
    }

    merge_owned_hooks_into(config, managed)

    hooks = config.get("hooks")
    assert isinstance(hooks, dict)
    assert "PreToolUse" in hooks


def test_backup_existing_file_creates_sibling_backup(tmp_path: Path) -> None:
    original = tmp_path / "settings.json"
    original.write_text('{"key": "value"}', encoding="utf-8")

    backup_path = backup_existing_file(original)

    assert backup_path is not None
    assert backup_path.exists()
    assert backup_path.read_text(encoding="utf-8") == '{"key": "value"}'


def test_backup_existing_file_returns_none_when_file_absent(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"

    result = backup_existing_file(missing)

    assert result is None


def test_backup_existing_file_and_report_prints_backup_path(
    tmp_path: Path, capsys: Any
) -> None:
    original = tmp_path / "settings.json"
    original.write_text("{}", encoding="utf-8")

    backup_existing_file_and_report(original, "settings")

    output = capsys.readouterr().out
    assert "Backed up" in output


def test_write_json_with_backup_writes_formatted_json(tmp_path: Path) -> None:
    target = tmp_path / "output.json"
    payload: dict[str, object] = {"hooks": {}, "version": 1}

    write_json_with_backup(target, payload, "output")

    written = json.loads(target.read_text(encoding="utf-8"))
    assert written == payload
