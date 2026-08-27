"""OMP extension installer support."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import slopgate.installer._shared
from slopgate.constants import INSTALL_SCOPE_USER
from slopgate.installer._install_scope import (
    ResidualInstallScopeWarning,
    normalize_install_scope,
    resolve_project_root,
    resolve_scoped_install_paths,
    scope_paths,
    warn_residual_install_scope,
)
from slopgate.installer._omp_support import (
    ArtifactSnapshot,
    MANIFEST_TEXT,
    OMP_OWNERSHIP_MARKERS,
    OmpSiteSnapshot,
    _is_owned_omp_index,
    _restore_omp_site,
    _snapshot_omp_site,
    omp_extension_has_owned_slopgate,
)
from slopgate.installer._shared import (
    ContainedWrite,
    InstallAt,
    UnsafeInstallPathError,
    contained_scope_root,
    print_binary_install_summary,
    report_contained_install_path,
    write_contained_text,
)
from slopgate.installer.template_rendering import InvocationTemplateRenderer
from slopgate.resources import resource_path

_EXTENSION_DIR_NAME = "omp-slopgate"
_INDEX_NAME = "index.ts"
_MANIFEST_NAME = "package.json"
_ARGV_PLACEHOLDER = '["__SLOPGATE_BIN__"]'


@dataclass(frozen=True, slots=True)
class OmpInstallMaterial:
    """Rendered extension content and the binary used to produce it."""

    content: str
    binary: str


render_omp_extension = InvocationTemplateRenderer(
    _ARGV_PLACEHOLDER,
    "OMP extension template is missing the slopgate binary placeholder",
)


def omp_agent_dir() -> Path:
    """Resolve OMP's active user agent directory and containment root."""
    configured = os.environ.get("PI_CODING_AGENT_DIR")
    if configured and Path(configured).is_absolute():
        return Path(configured)
    return Path.home() / ".omp" / "agent"


def omp_user_extension_path() -> Path:
    return omp_agent_dir() / "extensions" / _EXTENSION_DIR_NAME / _INDEX_NAME


def omp_project_extension_path(project_root: Path) -> Path:
    return project_root / ".omp" / "extensions" / _EXTENSION_DIR_NAME / _INDEX_NAME


def _site_is_owned_or_absent(target: Path) -> bool:
    for path, label in (
        (target, "OMP extension"),
        (target.with_name(_MANIFEST_NAME), "OMP extension manifest"),
    ):
        if path.exists() and not omp_extension_has_owned_slopgate(path):
            print(f"Refusing to replace unrecognized {label}: {path}")
            return False
    return True


def _install_omp_at(
    target: Path,
    material: OmpInstallMaterial,
    site: InstallAt,
    snapshot: OmpSiteSnapshot,
) -> int:
    manifest_path = target.with_name(_MANIFEST_NAME)
    for path in (target, manifest_path):
        if report_contained_install_path(path, site.root) is None:
            return 1
    if not _site_is_owned_or_absent(target):
        return 1
    if site.dry_run:
        print(f"Would write: {target}")
        print(f"Would write: {manifest_path}")
        print(f"Binary: {material.binary}")
        return 0
    write = ContainedWrite(root=site.root, label="file", backup=False)
    try:
        written = write_contained_text(target, material.content, write)
        _ = write_contained_text(manifest_path, MANIFEST_TEXT, write)
    except (OSError, UnsafeInstallPathError) as exc:
        print(str(exc))
        restore_status = _restore_omp_site(target, snapshot)
        if restore_status != 0:
            print(
                f"Incomplete OMP rollback: {target}: {restore_status}",
                file=sys.stderr,
            )
        return 1
    print_binary_install_summary(
        f"Installed slopgate OMP extension to {written}", material.binary
    )
    return 0


def _rollback_omp_sites(
    completed: list[Path], snapshots: dict[Path, OmpSiteSnapshot]
) -> int:
    incomplete = False
    for path in completed:
        try:
            status = _restore_omp_site(path, snapshots[path])
        except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
            incomplete = True
            print(f"Incomplete OMP rollback: {path}: {exc}", file=sys.stderr)
            continue
        if status != 0:
            incomplete = True
            print(f"Incomplete OMP rollback: {path}: {status}", file=sys.stderr)
    return int(incomplete)


def install_omp(
    dry_run: bool = False,
    *,
    scope: str = INSTALL_SCOPE_USER,
    project_root: Path | None = None,
) -> int:
    template = resource_path("omp_extension.ts")
    if not template.exists():
        print(f"OMP extension template not found at {template}")
        return 1
    root = resolve_project_root(project_root)
    binary = slopgate.installer._shared.find_binary()
    paths = resolve_scoped_install_paths(
        scope,
        project_root,
        user_path=omp_user_extension_path(),
        project_path_for_root=omp_project_extension_path,
    )
    try:
        template_text = template.read_text(encoding="utf-8")
        material = OmpInstallMaterial(
            content=render_omp_extension(template_text, binary), binary=binary
        )
    except (OSError, ValueError) as exc:
        print(str(exc))
        return 1
    completed: list[Path] = []
    snapshots: dict[Path, OmpSiteSnapshot] = {}
    for target in paths:
        site_root = contained_scope_root(
            target, project_root=root, user_root=omp_agent_dir()
        )
        try:
            snapshot = _snapshot_omp_site(target, site_root)
        except (OSError, UnsafeInstallPathError) as exc:
            print(str(exc))
            return _rollback_omp_sites(completed, snapshots) or 1
        snapshots[target] = snapshot
        status = _install_omp_at(
            target,
            material,
            InstallAt(root=site_root, dry_run=dry_run),
            snapshot,
        )
        if status != 0:
            return _rollback_omp_sites(completed, snapshots) or status
        completed.append(target)
    return 0


def _remove_owned_artifact(path: Path, label: str, *, dry_run: bool) -> int:
    if not path.exists():
        return 0
    if not omp_extension_has_owned_slopgate(path):
        print(f"Refusing to remove unrecognized {label}: {path}")
        return 1
    if dry_run:
        print(f"Would delete: {path}")
        return 0
    try:
        path.unlink()
    except OSError as exc:
        print(str(exc))
        return 1
    return 0


def _uninstall_omp_at(target: Path, *, dry_run: bool) -> int:
    status = 0
    for path, label in (
        (target, "OMP extension"),
        (target.with_name(_MANIFEST_NAME), "OMP extension manifest"),
    ):
        status = _remove_owned_artifact(path, label, dry_run=dry_run) or status
    if status != 0 or dry_run:
        return status
    try:
        target.parent.rmdir()
    except OSError:
        print(f"Removed slopgate OMP artifacts from {target.parent}")
        return 0
    print(f"Removed slopgate OMP extension directory {target.parent}")
    return 0


def uninstall_omp(
    dry_run: bool = False,
    *,
    scope: str = INSTALL_SCOPE_USER,
    project_root: Path | None = None,
) -> int:
    install_scope = normalize_install_scope(scope)
    root = resolve_project_root(project_root)
    paths = scope_paths(
        install_scope,
        user_path=omp_user_extension_path(),
        project_path=omp_project_extension_path(root),
    )
    for target in paths:
        status = _uninstall_omp_at(target, dry_run=dry_run)
        if status != 0:
            return status
    if not dry_run:
        warn_residual_install_scope(
            ResidualInstallScopeWarning(
                platform_label="OMP",
                scope=scope,
                user_path=omp_user_extension_path(),
                project_path=omp_project_extension_path(root),
                project_root=project_root,
                has_owned=omp_extension_has_owned_slopgate,
            )
        )
    return 0


__all__ = [
    "ArtifactSnapshot",
    "OMP_OWNERSHIP_MARKERS",
    "OmpSiteSnapshot",
    "_is_owned_omp_index",
    "install_omp",
    "omp_agent_dir",
    "omp_extension_has_owned_slopgate",
    "omp_project_extension_path",
    "omp_user_extension_path",
    "render_omp_extension",
    "uninstall_omp",
]
