from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.release_artifacts.support import REPO_ROOT, uv_binary

_BUILD_PROVENANCE = (
    REPO_ROOT / "build",
    REPO_ROOT / "src" / "ai_slopgate.egg-info",
)


@pytest.fixture(scope="module")
def release_dist(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    cache_dir = REPO_ROOT / "src" / "slopgate" / "resources" / "__pycache__"
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    planted = cache_dir / f"opencode_plugin.{worker}.pyc"
    cache_dir.mkdir(exist_ok=True)
    planted.write_bytes(b"slopgate-release-hygiene")
    dist_dir = tmp_path_factory.mktemp("dist")
    try:
        build = subprocess.run(
            [uv_binary(), "build", "--out-dir", str(dist_dir)],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert build.returncode == 0, build.stderr
        yield dist_dir
    finally:
        planted.unlink(missing_ok=True)
        if cache_dir.exists() and not any(cache_dir.iterdir()):
            cache_dir.rmdir()
        for leftover in _BUILD_PROVENANCE:
            shutil.rmtree(leftover, ignore_errors=True)
