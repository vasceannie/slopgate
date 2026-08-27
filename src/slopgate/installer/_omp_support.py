"""Artifact ownership and filesystem transactions for OMP installs."""

from __future__ import annotations

import json
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from slopgate._types import object_dict
from slopgate.constants import REPLACE
from slopgate.installer._shared import (
    UnsafeInstallPathError,
    require_contained_install_path,
)

OMP_OWNERSHIP_MARKERS = (
    "OMP Slopgate Extension",
    "const SLOPGATE_ARGV",
    "slopgate handle --platform omp",
)
_MANIFEST_NAME = "package.json"


class OmpManifestExtensions(TypedDict):
    extensions: list[str]


OmpManifestPeers = TypedDict(
    "OmpManifestPeers",
    {
        "@oh-my-pi/pi-coding-agent": str,
        "@oh-my-pi/pi-tui": str,
    },
)


class OmpManifestPayload(TypedDict):
    name: str
    private: bool
    type: str
    omp: OmpManifestExtensions
    peerDependencies: OmpManifestPeers


MANIFEST_PAYLOAD: OmpManifestPayload = {
    "name": "omp-slopgate",
    "private": True,
    "type": "module",
    "omp": {"extensions": ["./index.ts"]},
    "peerDependencies": {
        "@oh-my-pi/pi-coding-agent": "*",
        "@oh-my-pi/pi-tui": "*",
    },
}
MANIFEST_TEXT = json.dumps(MANIFEST_PAYLOAD, indent=2) + "\n"


@dataclass(frozen=True, slots=True)
class ArtifactSnapshot:
    """Original bytes and mode for one installer artifact."""

    existed: bool
    content: bytes | None
    mode: int | None


@dataclass(frozen=True, slots=True)
class OmpSiteSnapshot:
    """Original artifacts and transaction-created directory candidates for one site."""

    index: ArtifactSnapshot
    manifest: ArtifactSnapshot
    missing_dirs_before: tuple[Path, ...]


def _is_owned_omp_index(content: str) -> bool:
    """Return whether extension text contains all Slopgate ownership markers."""
    return all(marker in content for marker in OMP_OWNERSHIP_MARKERS)


def is_owned_omp_manifest(content: str) -> bool:
    """Return whether JSON content is exactly the canonical OMP manifest object."""
    try:
        parsed = object_dict(json.loads(content))
    except json.JSONDecodeError:
        return False
    return parsed == MANIFEST_PAYLOAD


def omp_extension_has_owned_slopgate(path: Path) -> bool:
    """Recognize only installer-owned OMP extension and manifest artifacts."""
    if not path.exists() or not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8", errors=REPLACE)
    except OSError:
        return False
    if path.name == _MANIFEST_NAME:
        return is_owned_omp_manifest(content)
    if path.name == "index.ts":
        return _is_owned_omp_index(content)
    return False


def _capture_artifact(path: Path) -> ArtifactSnapshot:
    if not path.exists():
        return ArtifactSnapshot(False, None, None)
    if not path.is_file():
        raise UnsafeInstallPathError(f"Refusing to replace non-file artifact: {path}")
    return ArtifactSnapshot(
        existed=True,
        content=path.read_bytes(),
        mode=stat.S_IMODE(path.stat().st_mode),
    )


def _missing_directories(package_dir: Path, root: Path) -> tuple[Path, ...]:
    _ = require_contained_install_path(package_dir / "index.ts", root)
    missing: list[Path] = []
    current = package_dir
    while not current.exists():
        missing.append(current)
        current = current.parent
    return tuple(missing)


def _snapshot_omp_site(target: Path, root: Path) -> OmpSiteSnapshot:
    """Capture both artifacts and every directory a contained write may create."""
    safe_index = require_contained_install_path(target, root)
    safe_manifest = require_contained_install_path(target.with_name(_MANIFEST_NAME), root)
    return OmpSiteSnapshot(
        index=_capture_artifact(safe_index),
        manifest=_capture_artifact(safe_manifest),
        missing_dirs_before=_missing_directories(safe_index.parent, root),
    )


def _restore_artifact(path: Path, snapshot: ArtifactSnapshot) -> None:
    if snapshot.existed:
        if snapshot.content is None or snapshot.mode is None:
            raise OSError(f"Incomplete snapshot for {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(snapshot.content)
        path.chmod(snapshot.mode)
        return
    if path.exists():
        path.unlink()


def _restore_omp_site(target: Path, snapshot: OmpSiteSnapshot) -> int:
    """Restore one site and remove only directories recorded as transaction-created."""
    status = 0
    for path, artifact in (
        (target, snapshot.index),
        (target.with_name(_MANIFEST_NAME), snapshot.manifest),
    ):
        try:
            _restore_artifact(path, artifact)
        except OSError:
            status = 1
    for directory in snapshot.missing_dirs_before:
        try:
            directory.rmdir()
        except FileNotFoundError:
            continue
        except OSError:
            status = 1
    return status


__all__ = [
    "ArtifactSnapshot",
    "MANIFEST_TEXT",
    "OMP_OWNERSHIP_MARKERS",
    "OmpSiteSnapshot",
    "_is_owned_omp_index",
    "_restore_omp_site",
    "_snapshot_omp_site",
    "omp_extension_has_owned_slopgate",
]
