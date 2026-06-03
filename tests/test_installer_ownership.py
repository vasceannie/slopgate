from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import vibeforcer.installer as installer_module
import vibeforcer.installer._shared as installer_shared


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
