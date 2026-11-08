"""Scope-safe migration from prior Pi loose extensions."""

from __future__ import annotations

from pathlib import Path

from slopgate.constants import INSTALL_SCOPE_PROJECT, INSTALL_SCOPE_USER
from slopgate.installer._shared import (
    UnsafeInstallPathError,
    remove_file_with_backup,
    require_contained_install_path,
)
from slopgate.installer.native.artifacts import (
    ArtifactSnapshot,
    capture_artifact,
    restore_artifact,
    unsafe_anchor_issue,
)
from slopgate.installer.native.model import LegacyCutover, LegacyRefusal, NativeRequest
from slopgate.installer.native.pi.legacy import (
    EXTENSION_DIR_NAME,
    EXTENSION_ENTRY_NAME,
    LEGACY_ENTRY_NAME,
    LEGACY_PACKAGE_ENTRY_NAME,
    pi_agent_dir,
    pi_extension_has_owned_slopgate,
    pi_has_owned_extension_entry,
)

__all__ = ["PiCutover"]

_CONFIG_NAME = "config.json"
_PACKAGE_NAME = "package.json"
_LEGACY_FILE_NAMES = (
    EXTENSION_ENTRY_NAME,
    LEGACY_PACKAGE_ENTRY_NAME,
    _CONFIG_NAME,
    _PACKAGE_NAME,
)


def _present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _extension_files(directory: Path) -> tuple[Path, ...]:
    return tuple(
        directory / name for name in _LEGACY_FILE_NAMES if _present(directory / name)
    )


def _owned_candidates(extensions: Path) -> tuple[tuple[Path, str], ...]:
    extension_dir = extensions / EXTENSION_DIR_NAME
    candidates = tuple(
        (path, f"legacy Pi package file {path.name}")
        for path in _extension_files(extension_dir)
    )
    standalone = extensions / LEGACY_ENTRY_NAME
    if _present(standalone):
        return (*candidates, (standalone, "legacy Pi extension"))
    return candidates


def _scope_roots(request: NativeRequest, scope: str) -> tuple[Path, Path]:
    if scope == INSTALL_SCOPE_USER:
        agent_dir = pi_agent_dir()
        return agent_dir / "extensions", agent_dir
    if scope == INSTALL_SCOPE_PROJECT:
        return request.root / ".pi" / "extensions", request.root
    raise ValueError(f"unsupported Pi scope: {scope}")


def _validate_extension_dir(directory: Path, contain_root: Path) -> None:
    if not _present(directory):
        return
    if directory.is_symlink() or not directory.is_dir():
        raise LegacyRefusal(
            f"Refusing unsafe legacy Pi extension directory: {directory}"
        )
    try:
        require_contained_install_path(directory, contain_root)
    except UnsafeInstallPathError as exc:
        raise LegacyRefusal(str(exc)) from exc
    extension_files = _extension_files(directory)
    if not extension_files:
        return
    if not pi_has_owned_extension_entry(directory):
        raise LegacyRefusal(
            f"Refusing to claim legacy Pi package from metadata alone: {directory} "
            "has no recognized Slopgate extension entry"
        )
    for path in extension_files:
        _validate_file(path, contain_root, "legacy Pi package file")


def _validate_file(path: Path, contain_root: Path, label: str) -> None:
    try:
        require_contained_install_path(path, contain_root)
    except UnsafeInstallPathError as exc:
        raise LegacyRefusal(str(exc)) from exc
    if not path.is_file() or not pi_extension_has_owned_slopgate(path):
        raise LegacyRefusal(f"Refusing to remove unrecognized {label}: {path}")


class PiCutover(LegacyCutover):
    """Capture, retire and restore only recognized prior Pi artifacts."""

    def __init__(self, request: NativeRequest) -> None:
        self._request = request
        self._snapshots: dict[Path, ArtifactSnapshot] = {}
        self._captured = False

    def preflight(self) -> None:
        for scope in self._request.scopes:
            if scope == INSTALL_SCOPE_PROJECT:
                issue = unsafe_anchor_issue(self._request.root / ".pi")
                if issue:
                    raise LegacyRefusal(issue)
            extensions, contain_root = _scope_roots(self._request, scope)
            extension_dir = extensions / EXTENSION_DIR_NAME
            _validate_extension_dir(extension_dir, contain_root)
            standalone = extensions / LEGACY_ENTRY_NAME
            if _present(standalone):
                _validate_file(standalone, contain_root, "legacy Pi extension")

    def describe(self) -> list[str]:
        actions: list[str] = []
        for scope in self._request.scopes:
            extensions, _ = _scope_roots(self._request, scope)
            candidates = _owned_candidates(extensions)
            if not candidates:
                actions.append(f"No legacy Pi artifacts for {scope} scope")
            actions.extend(
                f"Would remove {label}: {path}" for path, label in candidates
            )
        return actions

    def capture(self) -> None:
        for scope in self._request.scopes:
            extensions, _ = _scope_roots(self._request, scope)
            for path, _ in _owned_candidates(extensions):
                self._snapshots[path] = capture_artifact(path)
        self._captured = True

    def remove(self, scope: str) -> int:
        extensions, contain_root = _scope_roots(self._request, scope)
        for path, label in _owned_candidates(extensions):
            try:
                _validate_file(path, contain_root, label)
            except LegacyRefusal as exc:
                print(str(exc))
                return 1
            remove_file_with_backup(path, label)
        extension_dir = extensions / EXTENSION_DIR_NAME
        if extension_dir.is_dir():
            try:
                extension_dir.rmdir()
            except OSError:
                pass
        return 0

    def restore(self) -> int:
        if not self._captured:
            return 0
        status = 0
        for path, snapshot in self._snapshots.items():
            try:
                restore_artifact(path, snapshot)
            except OSError:
                status = 1
        return status
