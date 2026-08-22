"""Shared plants and refusal helpers for installer scope tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

import slopgate.installer._claude
import slopgate.installer._codex
import slopgate.installer._cursor
import slopgate.installer._opencode
import slopgate.installer._pi
import slopgate.installer._shared

KEEP_TEXT = "KEEP\n"


def stub_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )


def plant_opencode_project_symlink(tmp_path: Path, kind: str) -> Path:
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    external = outside_dir / ("secret.ts" if kind == "leaf" else "keep.txt")
    external.write_text(KEEP_TEXT, encoding="utf-8")
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


def refuse_opencode_project_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, dry_run: bool
) -> tuple[Path, Path]:
    stub_binary(monkeypatch)
    monkeypatch.chdir(tmp_path)
    external = plant_opencode_project_symlink(tmp_path, kind)
    outside_names = {path.name for path in external.parent.iterdir()}
    assert (
        slopgate.installer._opencode.install_opencode(
            dry_run=dry_run, scope="project"
        )
        == 1
    ), "project install must refuse symlink targets and parents"
    assert external.read_text(encoding="utf-8") == KEEP_TEXT, (
        "external symlink targets must remain unchanged"
    )
    assert {path.name for path in external.parent.iterdir()} == outside_names, (
        "install must not create files beside the external target"
    )
    plugin = tmp_path / ".opencode" / "plugins" / "slopgate-plugin.ts"
    return plugin, external


def plant_project_symlink(tmp_path: Path, relative_leaf: str, kind: str) -> Path:
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    external = outside_dir / ("secret" if kind == "leaf" else "keep.txt")
    external.write_text(KEEP_TEXT, encoding="utf-8")
    leaf = tmp_path / relative_leaf
    if kind == "leaf":
        leaf.parent.mkdir(parents=True)
        leaf.symlink_to(external)
        return external
    first = Path(relative_leaf).parts[0]
    (tmp_path / first).symlink_to(outside_dir)
    return external


def refuse_project_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    install: Callable[..., int],
    relative_leaf: str,
    kind: str,
) -> tuple[Path, Path]:
    stub_binary(monkeypatch)
    monkeypatch.chdir(tmp_path)
    external = plant_project_symlink(tmp_path, relative_leaf, kind)
    outside_names = {path.name for path in external.parent.iterdir()}
    assert install(dry_run=False, scope="project") == 1, (
        "project install must refuse symlink targets and parents"
    )
    assert external.read_text(encoding="utf-8") == KEEP_TEXT, (
        "external symlink targets must remain unchanged"
    )
    assert {path.name for path in external.parent.iterdir()} == outside_names, (
        "install must not create files beside the external target"
    )
    return tmp_path / relative_leaf, external


def plant_user_leaf_symlink(tmp_path: Path, relative_leaf: str) -> tuple[Path, Path]:
    outside = tmp_path / "outside" / "secret"
    outside.parent.mkdir()
    outside.write_text(KEEP_TEXT, encoding="utf-8")
    target = tmp_path / relative_leaf
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)
    return target, outside


OPENCODE_LEAF_CASES = [
    pytest.param(False, id="leaf-symlink"),
    pytest.param(True, id="leaf-symlink-dry-run"),
]
OPENCODE_PARENT_CASES = [
    pytest.param("opencode-dir", False, id="opencode-dir-symlink"),
    pytest.param("plugins-dir", False, id="plugins-dir-symlink"),
    pytest.param("opencode-dir", True, id="opencode-dir-symlink-dry-run"),
]
PROJECT_INSTALLERS = [
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
]
USER_INSTALLERS = [
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
]
