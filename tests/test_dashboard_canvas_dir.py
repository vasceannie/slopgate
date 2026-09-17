"""Guard the ForceDash canvas directory against retired-path drift."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANVAS_ENV = "SLOPGATE_CANVAS_DIR"
EXPECTED_DEFAULT = Path.home() / ".local/share/slopgate/forcedash"

PROBE = (
    "import sys; sys.path[:0] = ['dashboard/scripts', '.'];"
    "from forcedash_server import config;"
    "from build_standalone import projection;"
    "print(config.CANVAS_DIR);"
    "print(projection.CANVAS_DEPLOY)"
)


def _probe_canvas_dirs(override: str | None) -> tuple[Path, Path]:
    """Resolve the served and deployed canvas paths in a subprocess."""
    env = dict(os.environ)
    if override is None:
        env.pop(CANVAS_ENV, None)
    else:
        env[CANVAS_ENV] = override
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    served, deployed = result.stdout.split()
    return Path(served), Path(deployed)


def test_canvas_paths_leave_the_retired_openclaw_tree() -> None:
    served, deployed = _probe_canvas_dirs(None)
    assert served == deployed == EXPECTED_DEFAULT
    assert ".openclaw" not in str(served)


def test_canvas_paths_honour_the_env_override(tmp_path: Path) -> None:
    override = str(tmp_path / "canvas")
    served, deployed = _probe_canvas_dirs(override)
    assert served == deployed == tmp_path / "canvas"
