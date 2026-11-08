"""Earlier OMP extension discovery and scope-safe retirement."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from slopgate.constants import INSTALL_SCOPE_PROJECT, INSTALL_SCOPE_USER
from slopgate.installer._shared import (
    UnsafeInstallPathError,
    remove_file_with_backup,
    require_contained_install_path,
)
from slopgate.installer._omp_support import omp_extension_has_owned_slopgate
from slopgate.installer.native.artifacts import (
    ArtifactSnapshot,
    capture_artifact,
    restore_artifact,
)
from slopgate.installer.native.model import LegacyCutover, LegacyRefusal, NativeRequest

_EXTENSION_DIR_NAME = "omp-slopgate"
_INDEX_NAME = "index.ts"
_MANIFEST_NAME = "package.json"


@dataclass(frozen=True, slots=True)
class _LegacyArtifact:
    scope: str
    path: Path
    root: Path


def omp_agent_dir() -> Path:
    """Resolve OMP's active user agent directory for extension migration."""
    configured = os.environ.get("PI_CODING_AGENT_DIR")
    if configured and Path(configured).is_absolute():
        return Path(configured)
    return Path.home() / ".omp" / "agent"


def omp_user_extension_path() -> Path:
    """Return the previous user-scope OMP extension entry path."""
    return omp_agent_dir() / "extensions" / _EXTENSION_DIR_NAME / _INDEX_NAME


def omp_project_extension_path(project_root: Path) -> Path:
    """Return the previous project-scope OMP extension entry path."""
    return project_root / ".omp" / "extensions" / _EXTENSION_DIR_NAME / _INDEX_NAME


def _scope_artifacts(request: NativeRequest, scope: str) -> tuple[_LegacyArtifact, ...]:
    if scope == INSTALL_SCOPE_USER:
        index = omp_user_extension_path()
        root = omp_agent_dir()
    elif scope == INSTALL_SCOPE_PROJECT:
        index = omp_project_extension_path(request.root)
        root = request.root
    else:
        return ()
    return tuple(
        _LegacyArtifact(scope, path, root)
        for path in (index, index.with_name(_MANIFEST_NAME))
    )


def _safe_path(artifact: _LegacyArtifact) -> Path:
    try:
        return require_contained_install_path(artifact.path, artifact.root)
    except UnsafeInstallPathError as exc:
        raise LegacyRefusal(str(exc)) from exc


def _remove_artifact(artifact: _LegacyArtifact) -> tuple[int, bool]:
    try:
        path = _safe_path(artifact)
        if not path.exists():
            return 0, False
        if not omp_extension_has_owned_slopgate(path):
            raise LegacyRefusal(
                f"Refusing to remove unrecognized legacy OMP artifact: {path}"
            )
        remove_file_with_backup(path, "legacy OMP artifact")
    except (LegacyRefusal, OSError, UnsafeInstallPathError) as exc:
        print(str(exc))
        return 1, False
    return 0, True


def _remove_empty_package_dir(artifact: _LegacyArtifact) -> None:
    try:
        artifact.path.parent.rmdir()
    except OSError:
        pass


def _restore_artifact(artifact: _LegacyArtifact, snapshot: ArtifactSnapshot) -> int:
    path = artifact.path
    try:
        safe_path = _safe_path(artifact)
        if safe_path.exists() and not omp_extension_has_owned_slopgate(safe_path):
            raise LegacyRefusal(
                f"Refusing to overwrite unrecognized rollback target: {safe_path}"
            )
        restore_artifact(safe_path, snapshot)
    except (LegacyRefusal, OSError, UnsafeInstallPathError) as exc:
        print(f"Incomplete legacy OMP rollback for {path}: {exc}")
        return 1
    return 0


class OmpLegacyCutover(LegacyCutover):
    """Preflight, back up, retire, and restore prior OMP extension files."""

    def __init__(self, request: NativeRequest) -> None:
        self._request = request
        self._artifacts = tuple(
            artifact
            for scope in request.scopes
            for artifact in _scope_artifacts(request, scope)
        )
        self._captured: dict[Path, ArtifactSnapshot] = {}
        self._removed: set[Path] = set()

    def preflight(self) -> None:
        for artifact in self._artifacts:
            path = _safe_path(artifact)
            if path.exists() and not omp_extension_has_owned_slopgate(path):
                raise LegacyRefusal(
                    f"Refusing to change unrecognized legacy OMP artifact: {path}"
                )

    def describe(self) -> list[str]:
        return [
            f"Would back up and remove legacy OMP artifact: {artifact.path}"
            for artifact in self._artifacts
            if artifact.path.exists()
            and omp_extension_has_owned_slopgate(artifact.path)
        ]

    def capture(self) -> None:
        self._captured = {
            artifact.path: capture_artifact(_safe_path(artifact))
            for artifact in self._artifacts
        }

    def remove(self, scope: str) -> int:
        selected = tuple(a for a in self._artifacts if a.scope == scope)
        removed_any = False
        for artifact in selected:
            status, removed = _remove_artifact(artifact)
            if status != 0:
                return status
            if removed:
                self._removed.add(artifact.path)
                removed_any = True
        if selected and removed_any:
            _remove_empty_package_dir(selected[0])
        return 0

    def restore(self) -> int:
        status = 0
        for artifact in self._artifacts:
            if artifact.path not in self._removed:
                continue
            snapshot = self._captured.get(artifact.path)
            if snapshot is None or _restore_artifact(artifact, snapshot) != 0:
                status = 1
        return status


__all__ = [
    "OmpLegacyCutover",
    "omp_agent_dir",
    "omp_project_extension_path",
    "omp_user_extension_path",
]
