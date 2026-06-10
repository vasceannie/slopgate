from __future__ import annotations
import pytest
import json
from pathlib import Path
from typing import cast
from slopgate._types import (
    ObjectDict,
    is_object_dict,
    object_dict,
    object_list,
    string_value,
)
from slopgate.installer import cursor_hooks_block, install_cursor, uninstall_cursor
from slopgate.installer._cursor import cursor_user_hooks_path
import slopgate.installer._shared
from slopgate.installer._shared import HOOK_TIMEOUT_STANDARD
from tests.test_installer import command_includes_slopgate_handle


def _cursor_hooks_block_snapshot(binary: str) -> dict[str, object]:
    hooks = cursor_hooks_block(binary)
    shell_entry = hooks["beforeShellExecution"][0]
    return {
        "command": shell_entry["command"],
        "has_after_file_edit": "afterFileEdit" in hooks,
        "has_tab_hooks": "beforeTabFileRead" in hooks and "afterTabFileEdit" in hooks,
        "shell_fail_closed": shell_entry["failClosed"],
        "read_fail_closed": hooks["beforeReadFile"][0]["failClosed"],
        "tab_read_fail_closed": hooks["beforeTabFileRead"][0]["failClosed"],
        "after_edit_fail_closed": hooks["afterFileEdit"][0]["failClosed"],
        "mcp_fail_closed": hooks["beforeMCPExecution"][0]["failClosed"],
        "timeout": shell_entry["timeout"],
    }


def test_cursor_hooks_block_uses_native_events_and_cursor_platform() -> None:
    binary = "/tmp/Slopgate Bin/slopgate"
    assert _cursor_hooks_block_snapshot(binary) == {
        "command": slopgate.installer._shared.hook_command(
            binary, "handle", "--platform", "cursor"
        ),
        "has_after_file_edit": True,
        "has_tab_hooks": True,
        "shell_fail_closed": True,
        "read_fail_closed": False,
        "tab_read_fail_closed": False,
        "after_edit_fail_closed": False,
        "mcp_fail_closed": True,
        "timeout": HOOK_TIMEOUT_STANDARD,
    }


def _cursor_install_merge_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, int | list[str] | ObjectDict]:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    hooks_path = cursor_user_hooks_path()
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(
        json.dumps(
            {
                "version": 1,
                "hooks": {
                    "beforeShellExecution": [
                        {"command": "./existing.sh", "matcher": "npm"}
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    install_status = install_cursor(dry_run=False)
    parsed = object_dict(json.loads(hooks_path.read_text(encoding="utf-8")))
    hooks = object_dict(parsed.get("hooks"))
    before_shell = object_list(hooks.get("beforeShellExecution"))
    commands: list[str] = []
    for entry in before_shell:
        if not is_object_dict(entry):
            continue
        command = string_value(entry.get("command"))
        if command is not None:
            commands.append(command)
    backup_count = len(list(hooks_path.parent.glob("hooks.json.slopgate-bak-*")))
    uninstall_status = uninstall_cursor(dry_run=False)
    parsed_after_uninstall = object_dict(
        json.loads(hooks_path.read_text(encoding="utf-8"))
    )
    return {
        "install_status": install_status,
        "commands": commands,
        "backup_count": backup_count,
        "uninstall_status": uninstall_status,
        "remaining_hooks": object_dict(parsed_after_uninstall.get("hooks")),
    }


def test_cursor_install_merges_owned_hooks_without_clobbering_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _cursor_install_merge_snapshot(tmp_path, monkeypatch)
    commands = cast(list[str], snapshot["commands"])
    remaining_hooks = cast(ObjectDict, snapshot["remaining_hooks"])
    assert {
        "install_status": snapshot["install_status"],
        "keeps_existing": "./existing.sh" in commands,
        "installs_cursor": any(
            command_includes_slopgate_handle(command, "--platform", "cursor")
            for command in commands
        ),
        "backup_count": snapshot["backup_count"],
        "uninstall_status": snapshot["uninstall_status"],
        "remaining_hooks": remaining_hooks,
    } == {
        "install_status": 0,
        "keeps_existing": True,
        "installs_cursor": True,
        "backup_count": 1,
        "uninstall_status": 0,
        "remaining_hooks": {
            "beforeShellExecution": [{"command": "./existing.sh", "matcher": "npm"}]
        },
    }


def test_cursor_install_project_scope_writes_repo_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import slopgate.installer._cursor
    from slopgate.installer import _shared as installer_shared

    monkeypatch.setattr(installer_shared, "find_binary", lambda: "/tmp/slopgate")
    monkeypatch.chdir(tmp_path)
    status = slopgate.installer._cursor.install_cursor(dry_run=False, scope="project")
    hooks_path = tmp_path / ".cursor" / "hooks.json"
    parsed = json.loads(hooks_path.read_text(encoding="utf-8"))
    command = parsed["hooks"]["preToolUse"][0]["command"]
    assert status == 0
    assert "beforeTabFileRead" in parsed["hooks"]
    assert command_includes_slopgate_handle(command, "--platform", "cursor")
