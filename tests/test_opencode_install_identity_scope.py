from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate.installer import _opencode
import slopgate.installer._shared
from slopgate.util import platform


def _write_opencode_package_metadata(root: Path, version: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(
        json.dumps({"dependencies": {"@opencode-ai/plugin": version}}),
        encoding="utf-8",
    )


def _install_both_scope_plugins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, str, str]:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    user_root = tmp_path / ".config" / "opencode"
    project_root = tmp_path / "project"
    _write_opencode_package_metadata(user_root, "1.18.21")
    _write_opencode_package_metadata(project_root, "1.19.0")
    status = _opencode.install_opencode(
        dry_run=False, scope="both", project_root=project_root
    )
    user_plugin = (user_root / "plugins" / "slopgate-plugin.ts").read_text()
    project_plugin = (
        project_root / ".opencode" / "plugins" / "slopgate-plugin.ts"
    ).read_text()
    return status, user_plugin, project_plugin


def test_opencode_user_identity_uses_user_install_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status, user_plugin, _ = _install_both_scope_plugins(tmp_path, monkeypatch)
    expected = (
        '"install_scope":"user"',
        f'"install_root":{json.dumps(str(tmp_path / ".config" / "opencode"))}',
        '"plugin_declared_version":"1.18.21"',
    )

    assert status == 0, "user and project OpenCode installs should succeed"
    assert all(fragment in user_plugin for fragment in expected), (
        f"user identity did not use the user install root: {user_plugin}"
    )


def test_opencode_project_identity_uses_project_install_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status, _, project_plugin = _install_both_scope_plugins(tmp_path, monkeypatch)
    expected = (
        '"install_scope":"project"',
        f'"install_root":{json.dumps(str(tmp_path / "project"))}',
        '"plugin_declared_version":"1.19.0"',
    )

    assert status == 0, "user and project OpenCode installs should succeed"
    assert all(fragment in project_plugin for fragment in expected), (
        f"project identity did not use the project install root: {project_plugin}"
    )
