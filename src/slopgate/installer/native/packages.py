"""Durable staged runtime packages for native harness registration."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

import slopgate
from slopgate._types import object_dict
from slopgate.constants import PLATFORM_KEY
from slopgate.installer._shared import (
    ContainedWrite,
    UnsafeInstallPathError,
    require_contained_install_path,
    write_contained_text,
)
from slopgate.installer.native.artifacts import (
    ArtifactSnapshot,
    capture_artifact,
    missing_directories,
    remove_empty_directories,
    restore_artifact,
)
from slopgate.installer.native.model import SOURCE_KEY, VERSION_KEY

from slopgate.util.platform import user_data_dir

__all__ = [
    "MARKETPLACE_NAME",
    "owned_staging_present",
    "MarketplaceSpec",
    "OWNERSHIP_MANIFEST_NAME",
    "PackagePlan",
    "StagingError",
    "StagingSnapshot",
    "check_staging_owned",
    "marketplace_plan",
    "native_host_root",
    "package_plan",
    "restore_staging",
    "snapshot_staging",
    "staging_is_current",
    "write_staging",
]

MARKETPLACE_NAME = "slopgate-runtime"
OWNERSHIP_MANIFEST_NAME = ".slopgate-owned.json"
OWNERSHIP_SCHEMA_VERSION = 1
_CATALOG_FILE_NAME = "marketplace.json"
_MARKETPLACE_DIR = "marketplace"
_PACKAGE_DIR = "package"
_PLUGINS_DIR = "plugins"

PayloadRenderer = Callable[[str], dict[str, str]]


class StagingError(ValueError):
    """The staged package area is not recognizably owned by Slopgate."""


@dataclass(frozen=True, slots=True)
class MarketplaceSpec:
    """Host-specific description of a one-plugin local marketplace."""

    catalog_dir: str
    plugin_name: str
    description: str
    render: PayloadRenderer


@dataclass(frozen=True, slots=True)
class PackagePlan:
    """Everything Slopgate will stage for one host, computed without I/O."""

    host: str
    contain_root: Path
    entry_root: Path
    package_dir: Path
    version: str
    files: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class StagingSnapshot:
    """Prior bytes/modes of every path a staging write can touch."""

    artifacts: Mapping[Path, ArtifactSnapshot]
    missing_dirs: tuple[Path, ...]


def native_host_root(host: str) -> Path:
    """Return Slopgate's per-host staging area under its user data directory."""
    return user_data_dir("slopgate") / "native" / host


def _digest(data: str | bytes) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def _content_digest(base_version: str, files: Mapping[str, str]) -> str:
    hashes = {name: _digest(text) for name, text in sorted(files.items())}
    canonical = json.dumps(
        {"slopgate_version": base_version, "files": hashes},
        sort_keys=True,
        separators=(",", ":"),
    )
    return _digest(canonical)


def _versioned(render: PayloadRenderer) -> tuple[str, str, dict[str, str]]:
    """Return digest, final version and payload files for a renderer."""
    base_version = slopgate.__version__
    digest = _content_digest(base_version, render(base_version))
    version = f"{base_version}+local.{digest}"
    return digest, version, render(version)


def marketplace_plan(host: str, spec: MarketplaceSpec) -> PackagePlan:
    """Plan a one-plugin local marketplace with an immutable payload snapshot."""
    digest, version, payload = _versioned(spec.render)
    contain_root = native_host_root(host)
    entry_root = contain_root / _MARKETPLACE_DIR
    plugin_rel = f"{_PLUGINS_DIR}/{spec.plugin_name}/{digest}"
    catalog = {
        "name": MARKETPLACE_NAME,
        "owner": {"name": "Slopgate"},
        "plugins": [
            {
                "name": spec.plugin_name,
                SOURCE_KEY: f"./{plugin_rel}",
                "description": spec.description,
                VERSION_KEY: version,
            }
        ],
    }
    files = {f"{plugin_rel}/{name}": text for name, text in payload.items()}
    catalog_name = f"{spec.catalog_dir}/{_CATALOG_FILE_NAME}"
    files[catalog_name] = json.dumps(catalog, indent=2) + "\n"
    return PackagePlan(
        host=host,
        contain_root=contain_root,
        entry_root=entry_root,
        package_dir=entry_root / plugin_rel,
        version=version,
        files=files,
    )


def package_plan(host: str, *, render: PayloadRenderer) -> PackagePlan:
    """Plan a single stable-path package that is refreshed in place."""
    _, version, payload = _versioned(render)
    contain_root = native_host_root(host)
    entry_root = contain_root / _PACKAGE_DIR
    return PackagePlan(
        host=host,
        contain_root=contain_root,
        entry_root=entry_root,
        package_dir=entry_root,
        version=version,
        files=payload,
    )


def _manifest_path(plan: PackagePlan) -> Path:
    return plan.entry_root / OWNERSHIP_MANIFEST_NAME


def _manifest_text(plan: PackagePlan) -> str:
    manifest = {
        "schema_version": OWNERSHIP_SCHEMA_VERSION,
        PLATFORM_KEY: plan.host,
        "files": {name: _digest(text) for name, text in sorted(plan.files.items())},
    }
    return json.dumps(manifest, indent=2) + "\n"


def _planned_paths(plan: PackagePlan) -> dict[Path, str]:
    paths = {plan.entry_root / name: text for name, text in plan.files.items()}
    paths[_manifest_path(plan)] = _manifest_text(plan)
    return paths


def _recorded_files(plan: PackagePlan) -> dict[str, object]:
    path = _manifest_path(plan)
    try:
        parsed = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise StagingError(
            "Refusing to use unrecognized staging area (unreadable ownership "
            f"manifest): {path}"
        ) from exc
    manifest = object_dict(parsed)
    files = manifest.get("files")
    if (
        manifest.get("schema_version") != OWNERSHIP_SCHEMA_VERSION
        or manifest.get(PLATFORM_KEY) != plan.host
        or not isinstance(files, dict)
        or not files
    ):
        raise StagingError(
            "Refusing to use staging area with a foreign or malformed ownership "
            f"manifest: {path}"
        )
    return cast(dict[str, object], files)


def owned_staging_present(host: str) -> bool:
    """Whether a valid Slopgate ownership manifest exists for this host's staging."""
    contain_root = native_host_root(host)
    for entry in (_MARKETPLACE_DIR, _PACKAGE_DIR):
        try:
            entry_root = contain_root / entry
            probe = PackagePlan(host, contain_root, entry_root, entry_root, "", {})
            if not _manifest_path(probe).is_file():
                continue
            _recorded_files(probe)
            check_staging_owned(probe)
        except (StagingError, OSError):
            continue
        return True
    return False


def _safe_recorded_path(plan: PackagePlan, name: str) -> Path:
    """Resolve a manifest key to a regular, contained, non-symlink staged file."""
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise StagingError(f"Refusing unsafe ownership manifest path: {name!r}")
    try:
        path = require_contained_install_path(
            plan.entry_root.joinpath(*relative.parts), plan.entry_root
        )
    except UnsafeInstallPathError as exc:
        raise StagingError(str(exc)) from exc
    if not path.is_file():
        raise StagingError(
            f"Refusing to overwrite modified Slopgate staging file: {path}"
        )
    return path


def check_staging_owned(plan: PackagePlan) -> None:
    """Raise ``StagingError`` unless the staging area is absent or Slopgate-owned."""
    try:
        require_contained_install_path(plan.entry_root, plan.contain_root)
    except UnsafeInstallPathError as exc:
        raise StagingError(str(exc)) from exc
    if not plan.entry_root.exists():
        return
    if not plan.entry_root.is_dir():
        raise StagingError(
            f"Refusing to replace non-directory staging path: {plan.entry_root}"
        )
    if not any(plan.entry_root.iterdir()):
        return
    for name, digest in _recorded_files(plan).items():
        path = _safe_recorded_path(plan, name)
        if not isinstance(digest, str) or _digest(path.read_bytes()) != digest:
            raise StagingError(
                f"Refusing to overwrite modified Slopgate staging file: {path}"
            )


def staging_is_current(plan: PackagePlan) -> bool:
    """Return whether every planned file already exists with identical content."""
    for path, text in _planned_paths(plan).items():
        try:
            if path.read_text(encoding="utf-8") != text:
                return False
        except OSError:
            return False
    return True


def _missing_staging_dirs(plan: PackagePlan) -> tuple[Path, ...]:
    directories: dict[Path, None] = {}
    for path in _planned_paths(plan):
        for directory in missing_directories(path.parent):
            directories[directory] = None
    return tuple(sorted(directories, key=lambda item: len(item.parts), reverse=True))


def snapshot_staging(plan: PackagePlan) -> StagingSnapshot:
    """Capture every path a staging write may modify, and directories it may create."""
    artifacts: dict[Path, ArtifactSnapshot] = {}
    for path in _planned_paths(plan):
        safe = require_contained_install_path(path, plan.contain_root)
        artifacts[safe] = capture_artifact(safe)
    return StagingSnapshot(
        artifacts=artifacts, missing_dirs=_missing_staging_dirs(plan)
    )


def write_staging(plan: PackagePlan) -> None:
    """Atomically write the planned payload, catalog and ownership manifest."""
    write = ContainedWrite(
        root=plan.contain_root,
        label="native package",
        backup=False,
        exact_newlines=True,
    )
    for path, text in _planned_paths(plan).items():
        _ = write_contained_text(path, text, write)


def restore_staging(snapshot: StagingSnapshot) -> int:
    """Roll staged files back to their captured state; return 1 when incomplete."""
    status = 0
    for path, artifact in snapshot.artifacts.items():
        try:
            restore_artifact(path, artifact)
        except OSError:
            status = 1
    return remove_empty_directories(snapshot.missing_dirs) or status
