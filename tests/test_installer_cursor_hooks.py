from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from slopgate.installer import _cursor_hooks_block, _install_cursor, _uninstall_cursor
from slopgate.installer._cursor import _cursor_hooks_path
from slopgate.installer._shared import HOOK_TIMEOUT_STANDARD


def _cursor_hooks_block_snapshot(binary: str) -> dict[str, object]:
    hooks = _cursor_hooks_block(binary)
    shell_entry = hooks["beforeShellExecution"][0]
    return {
        "command": shell_entry["command"],
        "has_after_file_edit": "afterFileEdit" in hooks,
        "has_tab_hooks": "beforeTabFileRead" in hooks and "afterTabFileEdit" in hooks,
        "fail_closed": shell_entry["failClosed"],
        "timeout": shell_entry["timeout"],
    }


def test_cursor_hooks_block_uses_native_events_and_cursor_platform() -> None:
    assert _cursor_hooks_block_snapshot("/tmp/Slopgate Bin/slopgate") == {
        "command": "'/tmp/Slopgate Bin/slopgate' handle --platform cursor",
        "has_after_file_edit": True,
        "has_tab_hooks": True,
        "fail_closed": True,
        "timeout": HOOK_TIMEOUT_STANDARD,
    }


def _cursor_install_merge_snapshot(tmp_path: Path, monkeypatch: Any) -> dict[str, object]:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    import slopgate.installer._cursor as cursor_installer

    monkeypatch.setattr(cursor_installer, "find_binary", lambda: "/tmp/slopgate")
    hooks_path = _cursor_hooks_path()
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

    install_status = _install_cursor(dry_run=False)
    parsed = json.loads(hooks_path.read_text(encoding="utf-8"))
    commands = [entry["command"] for entry in parsed["hooks"]["beforeShellExecution"]]
    backup_count = len(list(hooks_path.parent.glob("hooks.json.slopgate-bak-*")))

    uninstall_status = _uninstall_cursor(dry_run=False)
    parsed_after_uninstall = json.loads(hooks_path.read_text(encoding="utf-8"))

    return {
        "install_status": install_status,
        "commands": commands,
        "backup_count": backup_count,
        "uninstall_status": uninstall_status,
        "remaining_hooks": parsed_after_uninstall["hooks"],
    }


def test_cursor_install_merges_owned_hooks_without_clobbering_existing(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    snapshot = _cursor_install_merge_snapshot(tmp_path, monkeypatch)
    assert {
        "install_status": snapshot["install_status"],
        "keeps_existing": "./existing.sh" in snapshot["commands"],
        "installs_cursor": any(
            "handle --platform cursor" in command for command in snapshot["commands"]
        ),
        "backup_count": snapshot["backup_count"],
        "uninstall_status": snapshot["uninstall_status"],
        "remaining_hooks": snapshot["remaining_hooks"],
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
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    import slopgate.installer._cursor as cursor_installer

    monkeypatch.setattr(cursor_installer, "find_binary", lambda: "/tmp/slopgate")
    monkeypatch.chdir(tmp_path)

    status = cursor_installer._install_cursor(dry_run=False, scope="project")
    hooks_path = tmp_path / ".cursor" / "hooks.json"
    parsed = json.loads(hooks_path.read_text(encoding="utf-8"))
    command = parsed["hooks"]["preToolUse"][0]["command"]

    assert status == 0
    assert "beforeTabFileRead" in parsed["hooks"]
    assert command.endswith("handle --platform cursor")
