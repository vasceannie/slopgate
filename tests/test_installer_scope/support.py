"""Shared plants and refusal helpers for installer scope tests."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

import pytest

import slopgate.installer
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
        slopgate.installer.install_platform(
            "opencode", dry_run=dry_run, install_scope="project"
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
    assert install(dry_run=False, install_scope="project") == 1, (
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


def refuse_user_leaf_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    install: Callable[..., int],
    relative_leaf: str,
) -> tuple[int, Path, Path]:
    """Isolate user host config, plant an escaping leaf, and run installer preflight."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path / ".pi" / "agent"))
    stub_binary(monkeypatch)
    target, outside = plant_user_leaf_symlink(tmp_path, relative_leaf)
    status = install(dry_run=False, install_scope="user")
    return status, target, outside


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
        (
            partial(slopgate.installer.install_platform, "claude"),
            ".claude/settings.json",
        ),
        id="claude",
    ),
    pytest.param(
        (
            partial(slopgate.installer.install_platform, "cursor"),
            ".cursor/hooks.json",
        ),
        id="cursor",
    ),
    pytest.param(
        (
            partial(slopgate.installer.install_platform, "codex"),
            ".codex/hooks.json",
        ),
        id="codex",
    ),
    pytest.param(
        (
            partial(slopgate.installer.install_platform, "pi"),
            ".pi/extensions/pi-slopgate/index.ts",
        ),
        id="pi",
    ),
    pytest.param(
        (
            partial(slopgate.installer.install_platform, "omp"),
            ".omp/extensions/omp-slopgate/index.ts",
        ),
        id="omp",
    ),
]
USER_INSTALLERS = [
    pytest.param(
        partial(slopgate.installer.install_platform, "claude"),
        ".claude/settings.json",
        id="claude",
    ),
    pytest.param(
        partial(slopgate.installer.install_platform, "cursor"),
        ".cursor/hooks.json",
        id="cursor",
    ),
    pytest.param(
        partial(slopgate.installer.install_platform, "codex"),
        ".codex/hooks.json",
        id="codex",
    ),
    pytest.param(
        partial(slopgate.installer.install_platform, "pi"),
        ".pi/agent/extensions/pi-slopgate/index.ts",
        id="pi",
    ),
]
