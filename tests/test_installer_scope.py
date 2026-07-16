"""Install-scope tests for Claude, Codex, OpenCode, and Cursor harnesses."""

from __future__ import annotations
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, strategies

from slopgate.installer import install_platform, uninstall_platform
import slopgate.installer._claude
import slopgate.installer._codex
import slopgate.installer._cursor
import slopgate.installer._opencode
import slopgate.installer._shared
import slopgate.installer._suite
from slopgate.installer._install_scope import (
    ResidualInstallScopeWarning,
    normalize_install_scope,
    resolve_project_root,
    resolve_scoped_install_paths,
    scope_paths,
    warn_residual_install_scope,
)
from slopgate.installer._opencode import PLUGIN_OWNERSHIP_MARKERS


def test_claude_project_scope_writes_repo_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    monkeypatch.chdir(tmp_path)
    assert (
        slopgate.installer._claude.install_claude(dry_run=False, scope="project") == 0
    )
    settings_path = tmp_path / ".claude" / "settings.json"
    parsed = json.loads(settings_path.read_text(encoding="utf-8"))
    commands = [
        hook["command"]
        for entries in parsed["hooks"].values()
        for entry in entries
        for hook in entry["hooks"]
    ]
    assert any(("handle" in command for command in commands))


def test_codex_project_scope_writes_repo_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    monkeypatch.chdir(tmp_path)
    assert slopgate.installer._codex.install_codex(dry_run=False, scope="project") == 0
    hooks_path = tmp_path / ".codex" / "hooks.json"
    parsed = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert "PreToolUse" in parsed["hooks"]


def test_opencode_project_scope_writes_repo_plugin(
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
    content = plugin_path.read_text(encoding="utf-8")
    assert all((marker in content for marker in PLUGIN_OWNERSHIP_MARKERS))


def test_cursor_project_scope_still_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    monkeypatch.chdir(tmp_path)
    assert (
        slopgate.installer._cursor.install_cursor(dry_run=False, scope="project") == 0
    )
    assert (tmp_path / ".cursor" / "hooks.json").exists()


def test_install_platform_rejects_invalid_scope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert install_platform("cursor", install_scope="workspace") == 1
    assert "install scope must be one of" in capsys.readouterr().out


def test_uninstall_platform_rejects_invalid_scope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert uninstall_platform("claude", install_scope="global") == 1
    assert "install scope must be one of" in capsys.readouterr().out


def test_install_scope_helpers_normalize_and_resolve_paths(tmp_path: Path) -> None:
    assert normalize_install_scope("both") == "both"
    assert resolve_project_root(tmp_path) == tmp_path.resolve()
    user_path = tmp_path / "user.json"
    project_path = tmp_path / "project.json"
    assert scope_paths("both", user_path=user_path, project_path=project_path) == [
        user_path,
        project_path,
    ]


def test_resolve_scoped_install_paths_builds_project_path(tmp_path: Path) -> None:
    user_path = tmp_path / "user.json"
    paths = resolve_scoped_install_paths(
        "project",
        tmp_path,
        user_path=user_path,
        project_path_for_root=lambda root: root / "project.json",
    )
    assert paths == [tmp_path.resolve() / "project.json"], (
        "resolve_scoped_install_paths should normalize scope and resolve project root"
    )


def test_project_scope_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / ".opencode").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes project root"):
        resolve_scoped_install_paths(
            "project",
            tmp_path,
            user_path=tmp_path / "user-plugin.ts",
            project_path_for_root=lambda root: root / ".opencode/plugins/plugin.ts",
        )


def test_shared_writer_rejects_symlink_target(tmp_path: Path) -> None:
    victim = tmp_path / "victim.json"
    victim.write_text("original", encoding="utf-8")
    target = tmp_path / "settings.json"
    target.symlink_to(victim)
    with pytest.raises(OSError, match="symlink"):
        slopgate.installer._shared.write_json_with_backup(
            target, {"hooks": {}}, "hooks"
        )
    assert victim.read_text(encoding="utf-8") == "original"


def test_warn_residual_install_scope_notes_project_hooks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
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


def test_discover_install_sites_project_scope_reports_project_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    sites = slopgate.installer._suite.discover_install_sites(
        include_missing=True,
        install_scope="project",
        project_root=tmp_path,
    )

    paths_by_platform = {site.platform: site.path for site in sites}
    assert paths_by_platform == {
        "claude": tmp_path / ".claude" / "settings.json",
        "codex": tmp_path / ".codex" / "hooks.json",
        "opencode": tmp_path / ".opencode" / "plugins" / "slopgate-plugin.ts",
        "cursor": tmp_path / ".cursor" / "hooks.json",
        "pi": tmp_path / ".pi" / "extensions" / "pi-slopgate" / "index.ts",
    }, "suite discovery should use project-local paths for project scope"


@given(
    install_scope=strategies.sampled_from(("user", "project", "both")),
    include_missing=strategies.booleans(),
)
def test_discover_install_sites_returns_unique_platforms_for_valid_scopes(
    install_scope: str,
    include_missing: bool,
) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        with patch.object(Path, "home", return_value=root / "home"):
            sites = slopgate.installer._suite.discover_install_sites(
                include_missing=include_missing,
                install_scope=install_scope,
                project_root=root,
            )

    platforms = [site.platform for site in sites]
    assert len(platforms) == len(set(platforms)), (
        "suite discovery should return each platform at most once"
    )
    assert set(platforms) <= {"claude", "codex", "opencode", "cursor", "pi"}, (
        "suite discovery should return only supported harness platforms"
    )


def test_install_suite_project_scope_dry_run_reports_project_sites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    status = slopgate.installer.install_suite(
        slopgate.installer.SuiteInstallOptions(
            dry_run=True,
            include_missing=True,
            with_autoupdate=False,
            install_scope="project",
            project_root=tmp_path,
        )
    )

    output = capsys.readouterr().out
    expected_fragments = (
        f"Installing claude hooks at {tmp_path / '.claude/settings.json'}",
        f"Installing codex hooks at {tmp_path / '.codex/hooks.json'}",
        f"Installing opencode hooks at "
        f"{tmp_path / '.opencode/plugins/slopgate-plugin.ts'}",
        f"Installing cursor hooks at {tmp_path / '.cursor/hooks.json'}",
        f"Installing pi hooks at {tmp_path / '.pi/extensions/pi-slopgate/index.ts'}",
    )
    assert (status, all(fragment in output for fragment in expected_fragments)) == (
        0,
        True,
    ), "install all project-scope dry-run should report project-local harness paths"
