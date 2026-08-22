"""Contained file writes and hook-file uninstall."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from slopgate.installer._shared.hooks import require_json_object
from slopgate.installer._shared.models import ContainedWrite, HooksUninstall
from slopgate.installer._shared.paths import (
    UnsafeInstallPathError,
    report_contained_install_path,
    require_contained_install_path,
)


def _ensure_real_parent_dirs(target: Path, root: Path) -> None:
    root_abs = root.resolve()
    relative = target.relative_to(root_abs)
    current = root_abs
    if not current.exists():
        current.mkdir(parents=True)
    if current.is_symlink() or not current.is_dir():
        raise UnsafeInstallPathError(
            f"Refusing to install through a symlink: {current}"
        )
    for part in relative.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise UnsafeInstallPathError(
                f"Refusing to install through a symlink: {current}"
            )
        if not current.exists():
            current.mkdir()
        if current.is_symlink() or not current.is_dir():
            raise UnsafeInstallPathError(
                f"Refusing to install through a symlink: {current}"
            )


def _replace_text_atomically(target: Path, content: str) -> None:
    parent = target.parent
    fd, tmp_name = tempfile.mkstemp(
        prefix=".slopgate-write-", suffix=".tmp", dir=str(parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if target.is_symlink():
            raise UnsafeInstallPathError(
                f"Refusing to install through a symlink: {target}"
            )
        os.replace(tmp_name, target)
    except Exception:
        if os.path.lexists(tmp_name):
            os.unlink(tmp_name)
        raise


def write_contained_text(target: Path, content: str, write: ContainedWrite) -> Path:
    """Atomically replace a file that stays inside root, optionally backing it up."""
    safe_target = require_contained_install_path(target, write.root)
    _ensure_real_parent_dirs(safe_target, write.root)
    if write.backup:
        backup_existing_file_and_report(safe_target, write.label)
    _replace_text_atomically(safe_target, content)
    return safe_target


def write_contained_json(
    target: Path, payload: object, *, root: Path, label: str
) -> Path:
    """Back up and atomically replace a JSON file that stays inside root."""
    return write_contained_text(
        target,
        json.dumps(payload, indent=2) + "\n",
        ContainedWrite(root=root, label=label),
    )


def backup_existing_file(path: Path) -> Path | None:
    """Create a timestamped sibling backup for an existing config/plugin file."""
    if not path.exists():
        return None
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    backup_path = path.with_name(f"{path.name}.slopgate-bak-{timestamp}")
    _ = shutil.copy2(path, backup_path)
    return backup_path


def backup_existing_file_and_report(path: Path, label: str) -> None:
    """Back up an existing file and print a concise installer status line."""
    backup_path = backup_existing_file(path)
    if backup_path is not None:
        print(f"Backed up existing {label} to {backup_path}")


def write_json_with_backup(path: Path, payload: object, label: str) -> None:
    """Back up an existing file, then write formatted JSON."""
    backup_existing_file_and_report(path, label)
    _ = path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def remove_file_with_backup(path: Path, label: str) -> None:
    backup_existing_file_and_report(path, label)
    path.unlink()
    print(f"Removed: {path}")


def uninstall_hooks_file(hooks_path: Path, request: HooksUninstall) -> int:
    """Remove slopgate-owned hook entries from a platform hooks.json file."""
    if (
        request.root is not None
        and report_contained_install_path(hooks_path, request.root) is None
    ):
        return 1
    if not hooks_path.exists():
        print(f"No {request.label} hooks found.")
        return 0
    if request.dry_run:
        print(f"Would remove slopgate hook entries from {hooks_path}")
        return 0

    existing = require_json_object(
        hooks_path, f"{request.label} hooks", action="modify"
    )
    if existing is None:
        return 1

    remaining_hooks = request.remove_owned(existing.get("hooks"))
    if remaining_hooks:
        existing["hooks"] = remaining_hooks
        _write_remaining_hooks(hooks_path, existing, request.root)
        print(f"Removed slopgate hooks from {hooks_path}")
        return 0

    existing.pop("hooks", None)
    if existing:
        _write_remaining_hooks(hooks_path, existing, request.root)
        print(f"Removed slopgate hooks from {hooks_path}")
        return 0

    remove_file_with_backup(hooks_path, "hooks")
    return 0


def _write_remaining_hooks(
    hooks_path: Path, existing: dict[str, object], root: Path | None
) -> None:
    if root is None:
        write_json_with_backup(hooks_path, existing, "hooks")
        return
    write_contained_json(hooks_path, existing, root=root, label="hooks")


def print_binary_install_summary(message: str, binary: str) -> None:
    print(message)
    print(f"Binary: {binary}")
