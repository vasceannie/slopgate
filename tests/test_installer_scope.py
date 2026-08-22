"""Install-scope tests for Claude, Codex, OpenCode, and Cursor harnesses."""

from __future__ import annotations
from collections.abc import Callable
import pytest
import json
from pathlib import Path
from slopgate.installer import install_platform, uninstall_platform
import slopgate.installer._claude
import slopgate.installer._codex
import slopgate.installer._cursor
import slopgate.installer._opencode
import slopgate.installer._pi
import slopgate.installer._shared
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


def _plant_opencode_project_symlink(tmp_path: Path, kind: str) -> Path:
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    external = outside_dir / ("secret.ts" if kind == "leaf" else "keep.txt")
    external.write_text("KEEP\n", encoding="utf-8")
    plugin = tmp_path / ".opencode" / "plugins" / "slopgate-plugin.ts"
    if kind == "leaf":
        plugin.parent.mkdir(parents=True)
        plugin.symlink_to(external)
    elif kind == "opencode-dir":
        (tmp_path / ".opencode").symlink_to(outside_dir)
    else:
        (tmp_path / ".opencode").mkdir()
        (tmp_path / ".opencode" / "plugins").symlink_to(outside_dir)
    return external


@pytest.mark.parametrize(
    ("kind", "dry_run"),
    [
        pytest.param("leaf", False, id="leaf-symlink"),
        pytest.param("opencode-dir", False, id="opencode-dir-symlink"),
        pytest.param("plugins-dir", False, id="plugins-dir-symlink"),
        pytest.param("leaf", True, id="leaf-symlink-dry-run"),
        pytest.param("opencode-dir", True, id="opencode-dir-symlink-dry-run"),
    ],
)
def test_opencode_project_scope_refuses_symlink_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    dry_run: bool,
) -> None:
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    monkeypatch.chdir(tmp_path)
    external = _plant_opencode_project_symlink(tmp_path, kind)
    outside_names = {path.name for path in external.parent.iterdir()}
    assert (
        slopgate.installer._opencode.install_opencode(
            dry_run=dry_run, scope="project"
        )
        == 1
    ), "project install must refuse symlink targets and parents"
    assert external.read_text(encoding="utf-8") == "KEEP\n", (
        "external symlink targets must remain unchanged"
    )
    assert {path.name for path in external.parent.iterdir()} == outside_names, (
        "install must not create files beside the external target"
    )
    plugin = tmp_path / ".opencode" / "plugins" / "slopgate-plugin.ts"
    if kind == "leaf":
        assert plugin.is_symlink(), "the planted leaf symlink must not be replaced"


def _plant_project_symlink(tmp_path: Path, relative_leaf: str, kind: str) -> Path:
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    external = outside_dir / ("secret" if kind == "leaf" else "keep.txt")
    external.write_text("KEEP\n", encoding="utf-8")
    leaf = tmp_path / relative_leaf
    if kind == "leaf":
        leaf.parent.mkdir(parents=True)
        leaf.symlink_to(external)
        return external
    first = Path(relative_leaf).parts[0]
    (tmp_path / first).symlink_to(outside_dir)
    return external


@pytest.mark.parametrize(
    ("install", "relative_leaf"),
    [
        pytest.param(
            slopgate.installer._claude.install_claude,
            ".claude/settings.json",
            id="claude",
        ),
        pytest.param(
            slopgate.installer._cursor.install_cursor,
            ".cursor/hooks.json",
            id="cursor",
        ),
        pytest.param(
            slopgate.installer._codex.install_codex,
            ".codex/hooks.json",
            id="codex",
        ),
        pytest.param(
            slopgate.installer._pi.install_pi,
            ".pi/extensions/pi-slopgate/index.ts",
            id="pi",
        ),
    ],
)
@pytest.mark.parametrize(
    "kind",
    [
        pytest.param("leaf", id="leaf-symlink"),
        pytest.param("parent", id="parent-dir-symlink"),
    ],
)
def test_project_scope_refuses_symlink_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    install: Callable[..., int],
    relative_leaf: str,
    kind: str,
) -> None:
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    monkeypatch.chdir(tmp_path)
    external = _plant_project_symlink(tmp_path, relative_leaf, kind)
    outside_names = {path.name for path in external.parent.iterdir()}
    assert install(dry_run=False, scope="project") == 1, (
        "project install must refuse symlink targets and parents"
    )
    assert external.read_text(encoding="utf-8") == "KEEP\n", (
        "external symlink targets must remain unchanged"
    )
    assert {path.name for path in external.parent.iterdir()} == outside_names, (
        "install must not create files beside the external target"
    )
    leaf = tmp_path / relative_leaf
    if kind == "leaf":
        assert leaf.is_symlink(), "the planted leaf symlink must not be replaced"


@pytest.mark.parametrize(
    ("install", "relative_leaf"),
    [
        pytest.param(
            slopgate.installer._claude.install_claude,
            ".claude/settings.json",
            id="claude",
        ),
        pytest.param(
            slopgate.installer._cursor.install_cursor,
            ".cursor/hooks.json",
            id="cursor",
        ),
        pytest.param(
            slopgate.installer._codex.install_codex,
            ".codex/hooks.json",
            id="codex",
        ),
        pytest.param(
            slopgate.installer._pi.install_pi,
            ".pi/agent/extensions/pi-slopgate/index.ts",
            id="pi",
        ),
    ],
)
def test_user_scope_refuses_leaf_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    install: Callable[..., int],
    relative_leaf: str,
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    outside = tmp_path / "outside" / "secret"
    outside.parent.mkdir()
    outside.write_text("KEEP\n", encoding="utf-8")
    target = tmp_path / relative_leaf
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)
    assert install(dry_run=False, scope="user") == 1, (
        "user install must refuse a leaf symlink"
    )
    assert outside.read_text(encoding="utf-8") == "KEEP\n", (
        "external symlink targets must remain unchanged"
    )
    assert target.is_symlink(), "the planted leaf symlink must not be replaced"


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
