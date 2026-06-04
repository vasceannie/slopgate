"""Install-scope tests for Claude, Codex, OpenCode, and Cursor harnesses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from slopgate.installer import install_platform, uninstall_platform

import slopgate.installer._claude as claude_installer
import slopgate.installer._codex as codex_installer
import slopgate.installer._cursor as cursor_installer
import slopgate.installer._opencode as opencode_installer
import slopgate.installer._shared as installer_shared
from slopgate.installer._install_scope import (
    ResidualInstallScopeWarning,
    normalize_install_scope,
    resolve_project_root,
    scope_paths,
    warn_residual_install_scope,
)
from slopgate.installer._opencode import _PLUGIN_OWNERSHIP_MARKERS


def test_claude_project_scope_writes_repo_settings(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(installer_shared, "find_binary", lambda: "/tmp/slopgate")
    monkeypatch.chdir(tmp_path)

    assert claude_installer._install_claude(dry_run=False, scope="project") == 0
    settings_path = tmp_path / ".claude" / "settings.json"
    parsed = json.loads(settings_path.read_text(encoding="utf-8"))
    commands = [
        hook["command"]
        for entries in parsed["hooks"].values()
        for entry in entries
        for hook in entry["hooks"]
    ]
    assert any("handle" in command for command in commands)


def test_codex_project_scope_writes_repo_hooks(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(installer_shared, "find_binary", lambda: "/tmp/slopgate")
    monkeypatch.chdir(tmp_path)

    assert codex_installer._install_codex(dry_run=False, scope="project") == 0
    hooks_path = tmp_path / ".codex" / "hooks.json"
    parsed = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert "PreToolUse" in parsed["hooks"]


def test_opencode_project_scope_writes_repo_plugin(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(installer_shared, "find_binary", lambda: "/tmp/slopgate")
    monkeypatch.chdir(tmp_path)

    assert opencode_installer._install_opencode(dry_run=False, scope="project") == 0
    plugin_path = tmp_path / ".opencode" / "plugins" / "slopgate-plugin.ts"
    content = plugin_path.read_text(encoding="utf-8")
    assert all(marker in content for marker in _PLUGIN_OWNERSHIP_MARKERS)


def test_cursor_project_scope_still_supported(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(installer_shared, "find_binary", lambda: "/tmp/slopgate")
    monkeypatch.chdir(tmp_path)

    assert cursor_installer._install_cursor(dry_run=False, scope="project") == 0
    assert (tmp_path / ".cursor" / "hooks.json").exists()


def test_install_platform_rejects_invalid_scope(capsys: Any) -> None:
    assert install_platform("cursor", install_scope="workspace") == 1
    assert "install scope must be one of" in capsys.readouterr().out


def test_uninstall_platform_rejects_invalid_scope(capsys: Any) -> None:
    assert uninstall_platform("claude", install_scope="global") == 1
    assert "install scope must be one of" in capsys.readouterr().out


def test_install_scope_helpers_normalize_and_resolve_paths(tmp_path: Path) -> None:
    assert normalize_install_scope("both") == "both"
    assert resolve_project_root(tmp_path) == tmp_path.resolve()
    user_path = tmp_path / "user.json"
    project_path = tmp_path / "project.json"
    assert scope_paths(
        "both",
        user_path=user_path,
        project_path=project_path,
    ) == [user_path, project_path]


def test_warn_residual_install_scope_notes_project_hooks(
    tmp_path: Path, capsys: Any
) -> None:
    user_path = tmp_path / "user" / "hooks.json"
    project_path = tmp_path / "project" / "hooks.json"
    user_path.parent.mkdir(parents=True)
    project_path.parent.mkdir(parents=True)
    user_path.write_text('{"hooks": {}}', encoding="utf-8")
    project_path.write_text('{"hooks": {}}', encoding="utf-8")

    warn_residual_install_scope(
        ResidualInstallScopeWarning(
            platform_label="cursor",
            scope="user",
            user_path=user_path,
            project_path=project_path,
            project_root=tmp_path,
            has_owned=lambda path: path == project_path,
        )
    )

    captured = capsys.readouterr()
    assert "remain at" in captured.out
    assert str(project_path) in captured.out
