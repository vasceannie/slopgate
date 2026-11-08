"""Project anchors beneath HOME must not inherit its user configuration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import slopgate.installer._omp
from slopgate.constants import INSTALL_SCOPE_PROJECT
from tests.omp_installer_support import OmpSandbox, prepare_omp_sandbox


def _project_beneath_home(home: Path) -> Path:
    project = home / "project with space"
    project.mkdir(parents=True)
    (home / ".omp" / "agent").mkdir(parents=True)
    return project


def _home_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[OmpSandbox, Path]:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path)
    return sandbox, _project_beneath_home(sandbox.home)


def _symlinked_home_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[OmpSandbox, Path]:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path)
    actual_home = tmp_path / "actual-home"
    actual_home.mkdir()
    sandbox.home.symlink_to(actual_home, target_is_directory=True)
    return sandbox, _project_beneath_home(sandbox.home)


def test_project_install_below_home_uses_local_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox, project = _home_project(tmp_path, monkeypatch)

    status = slopgate.installer._omp.install_omp(
        scope=INSTALL_SCOPE_PROJECT, project_root=project
    )

    assert status == 0, "a project below HOME must not inherit HOME's OMP anchor"
    assert (project / ".omp").is_dir(), (
        "project installation must create its local anchor"
    )
    assert (sandbox.home / ".omp" / "agent").is_dir(), (
        "project installation must preserve the user's OMP configuration"
    )


@pytest.mark.skipif(
    os.name == "nt", reason="Windows symlink creation requires host-specific privileges"
)
def test_project_install_below_symlinked_home_uses_local_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sandbox, project = _symlinked_home_project(tmp_path, monkeypatch)

    status = slopgate.installer._omp.install_omp(
        scope=INSTALL_SCOPE_PROJECT, project_root=project
    )

    assert status == 0, "a symlinked HOME boundary must prevent ancestor anchoring"
    assert (project.resolve() / ".omp").is_dir(), (
        "project installation must create the local anchor beneath resolved HOME"
    )
