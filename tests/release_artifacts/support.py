from __future__ import annotations

import shutil
import tarfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_SUFFIXES = (".pyc", ".pyo", ".pyd")


def uv_binary() -> str:
    binary = shutil.which("uv")
    assert binary is not None, "uv must be available to build release artifacts"
    return binary


def artifact_names(artifact: Path) -> list[str]:
    if artifact.suffix == ".whl":
        with zipfile.ZipFile(artifact) as archive:
            return archive.namelist()
    with tarfile.open(artifact) as archive:
        return archive.getnames()


def leaked_bytecode(names: list[str]) -> list[str]:
    return [
        name
        for name in names
        if "__pycache__" in Path(name).parts or name.endswith(FORBIDDEN_SUFFIXES)
    ]


def select_artifact(dist_dir: Path, kind: str) -> Path:
    matches = (
        list(dist_dir.glob("*.whl"))
        if kind == "wheel"
        else list(dist_dir.glob("*.tar.gz"))
    )
    assert matches, f"{kind} missing from {dist_dir}"
    return matches[0]
