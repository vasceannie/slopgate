from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.release_artifacts.support import (
    REPO_ROOT,
    artifact_names,
    leaked_bytecode,
    select_artifact,
    uv_binary,
)


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_isolated_artifact_excludes_bytecode(kind: str, release_dist: Path) -> None:
    leaked = leaked_bytecode(artifact_names(select_artifact(release_dist, kind)))
    assert leaked == [], f"{kind} contains bytecode: {leaked}"


def test_twine_accepts_isolated_artifacts(release_dist: Path) -> None:
    artifacts = [
        select_artifact(release_dist, "wheel"),
        select_artifact(release_dist, "sdist"),
    ]
    check = subprocess.run(
        [uv_binary(), "tool", "run", "twine", "check", "--strict", *artifacts],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stdout + check.stderr


def test_isolated_wheel_installs_selected_version(
    tmp_path: Path, release_dist: Path
) -> None:
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    bindir = venv / ("Scripts" if sys.platform == "win32" else "bin")
    # An inherited PYTHONPATH can expose src/ai_slopgate.egg-info from the build,
    # so pip treats the wheel as already installed and creates no console script.
    isolated_env = {
        name: value for name, value in os.environ.items() if name != "PYTHONPATH"
    }
    install = subprocess.run(
        [str(bindir / "pip"), "install", str(select_artifact(release_dist, "wheel"))],
        check=False,
        capture_output=True,
        env=isolated_env,
        text=True,
    )
    assert install.returncode == 0, install.stderr
    version = subprocess.run(
        [str(bindir / "slopgate"), "version"],
        check=False,
        capture_output=True,
        env=isolated_env,
        text=True,
    )
    assert version.returncode == 0, version.stderr
    from slopgate import __version__

    assert __version__ in version.stdout, version.stdout
