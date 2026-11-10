"""Installer containment must treat NTFS junctions like symlinks."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest

import slopgate.installer._opencode
from slopgate.constants import INSTALL_SCOPE_PROJECT
from slopgate.installer._shared import (
    ContainedWrite,
    HooksUninstall,
    UnsafeInstallPathError,
    remove_owned_hooks,
    require_contained_install_path,
    uninstall_hooks_file,
    write_contained_text,
)
from slopgate.installer.native.artifacts import unsafe_anchor_issue
from slopgate.installer.native.model import LegacyRefusal, NativeRequest
from slopgate.installer.native.omp import OmpMarketplaceHost
from slopgate.installer.native.pi.cutover import PiCutover
from slopgate.installer.native.pi.legacy import EXTENSION_DIR_NAME
from slopgate.util.platform import NTFS_JUNCTION_REPARSE_TAG

_OUTSIDE_HOOKS = '{"hooks": {}, "keep": true}\n'


class _JunctionStat(NamedTuple):
    st_mode: int
    st_reparse_tag: int


class _JunctionedProject(NamedTuple):
    root: Path
    outside: Path


def _emulate_windows_junction(monkeypatch: pytest.MonkeyPatch, link: Path) -> None:
    """Report a POSIX directory symlink the way Windows Python reports a junction."""
    real_lstat = Path.lstat
    real_is_symlink = Path.is_symlink

    def lstat(self: Path) -> os.stat_result | _JunctionStat:
        if self == link:
            return _JunctionStat(stat.S_IFDIR | 0o755, NTFS_JUNCTION_REPARSE_TAG)
        return real_lstat(self)

    def is_symlink(self: Path) -> bool:
        return False if self == link else real_is_symlink(self)

    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr(Path, "is_symlink", is_symlink)


def _junctioned_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, link_name: str
) -> _JunctionedProject:
    """Create project/<link_name> redirecting into an outside directory."""
    root = (tmp_path / "project").resolve()
    outside = tmp_path / "outside"
    outside.mkdir()
    root.mkdir()
    link = root / link_name
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside, target_is_directory=True)
    _emulate_windows_junction(monkeypatch, link)
    return _JunctionedProject(root, outside)


def test_contained_write_refuses_junctioned_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _junctioned_project(tmp_path, monkeypatch, "hooks")

    with pytest.raises(UnsafeInstallPathError, match="junction"):
        _ = write_contained_text(
            project.root / "hooks" / "hooks.json",
            "{}\n",
            ContainedWrite(root=project.root, label="hooks"),
        )

    assert list(project.outside.iterdir()) == [], (
        "a refused write must not create files behind the junction"
    )


def test_hooks_uninstall_refuses_junctioned_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _junctioned_project(tmp_path, monkeypatch, "hooks")
    external = project.outside / "hooks.json"
    _ = external.write_text(_OUTSIDE_HOOKS, encoding="utf-8")

    status = uninstall_hooks_file(
        project.root / "hooks" / "hooks.json",
        HooksUninstall(
            label="Codex", remove_owned=remove_owned_hooks, root=project.root
        ),
    )

    assert status == 1, "hook uninstall through a junction must be refused"
    assert external.read_text(encoding="utf-8") == _OUTSIDE_HOOKS, (
        "the hooks file behind the junction must stay unchanged"
    )


def test_opencode_project_uninstall_refuses_junctioned_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _junctioned_project(tmp_path, monkeypatch, ".opencode")
    plugin = project.outside / "plugins" / "slopgate-plugin.ts"
    plugin.parent.mkdir()
    owned = "\n".join(slopgate.installer._opencode.PLUGIN_OWNERSHIP_MARKERS) + "\n"
    _ = plugin.write_text(owned, encoding="utf-8")

    status = slopgate.installer._opencode.uninstall_opencode(
        scope="project", project_root=project.root
    )

    assert status == 1, "OpenCode uninstall must refuse a junctioned .opencode"
    assert plugin.read_text(encoding="utf-8") == owned, (
        "uninstall must not delete the plugin behind the junction"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS junctions are Windows-only")
def test_require_contained_install_path_rejects_real_ntfs_junction(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    _ = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(root / "plugins"), str(outside)],
        check=True,
        capture_output=True,
    )

    with pytest.raises(UnsafeInstallPathError, match="junction"):
        _ = require_contained_install_path(root / "plugins" / "x.ts", root)


def _omp_anchor_issue(root: Path) -> str | None:
    return OmpMarketplaceHost().project_anchor_issue(root)


def _claude_anchor_issue(root: Path) -> str | None:
    return unsafe_anchor_issue(root / ".claude")


class _AnchorCase(NamedTuple):
    link_name: str
    anchor_issue: Callable[[Path], str | None]
    expected: str


_OMP_ANCHOR = _AnchorCase(".omp", _omp_anchor_issue, "not a safe directory")
_ARTIFACT_ANCHOR = _AnchorCase(".claude", _claude_anchor_issue, "junctioned")
_ANCHOR_CASES = [
    pytest.param(_OMP_ANCHOR, False, id="omp"),
    pytest.param(_OMP_ANCHOR, True, id="omp-dangling"),
    pytest.param(_ARTIFACT_ANCHOR, False, id="artifact"),
    pytest.param(_ARTIFACT_ANCHOR, True, id="artifact-dangling"),
]


@pytest.mark.parametrize(("case", "dangling"), _ANCHOR_CASES)
def test_native_project_anchor_rejects_junction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: _AnchorCase, dangling: bool
) -> None:
    project = _junctioned_project(tmp_path, monkeypatch, case.link_name)
    if dangling:
        project.outside.rmdir()

    issue = case.anchor_issue(project.root)

    assert issue is not None and case.expected in issue, (
        "native project writes must not follow a junctioned config directory, "
        "even when its target is missing and could be recreated later"
    )


def test_pi_cutover_refuses_junctioned_legacy_extension_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    link_name = f".pi/extensions/{EXTENSION_DIR_NAME}"
    project = _junctioned_project(tmp_path, monkeypatch, link_name)
    cutover = PiCutover(NativeRequest(False, (INSTALL_SCOPE_PROJECT,), project.root))

    with pytest.raises(LegacyRefusal, match="unsafe legacy Pi extension directory"):
        cutover.preflight()
