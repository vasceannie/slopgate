"""Symlink-safe atomic installer writes."""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def safe_write_text(path: Path, content: str) -> None:
    """Atomically write text without following a target symlink."""
    if path.is_symlink():
        raise OSError(f"refusing to follow installer symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp_path = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}."
    )
    temp_path = Path(raw_temp_path)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            _ = handle.write(content)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def backup_existing_file(path: Path) -> Path | None:
    """Create a timestamped sibling backup without following symlinks."""
    if path.is_symlink():
        raise OSError(f"refusing to follow installer symlink: {path}")
    if not path.exists():
        return None
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    backup_path = path.with_name(f"{path.name}.slopgate-bak-{timestamp}")
    _ = shutil.copy2(path, backup_path)
    return backup_path


def backup_existing_file_and_report(path: Path, label: str) -> None:
    """Back up an existing file and print its installer status."""
    backup_path = backup_existing_file(path)
    if backup_path is not None:
        print(f"Backed up existing {label} to {backup_path}")
