"""Contained-path checks for installer writes."""

from __future__ import annotations

import os
from pathlib import Path


class UnsafeInstallPathError(ValueError):
    """Raised when an installer path escapes its selected root via a symlink."""


def require_contained_install_path(target: Path, root: Path) -> Path:
    """Return the path under resolved root if no post-root component is a symlink."""
    root_lex = Path(os.path.abspath(os.fspath(root)))
    target_lex = Path(os.path.abspath(os.fspath(target)))
    try:
        relative = target_lex.relative_to(root_lex)
    except ValueError as exc:
        raise UnsafeInstallPathError(
            f"Refusing to write outside the selected install root: {target_lex}"
        ) from exc
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise UnsafeInstallPathError(
            f"Refusing to write through a non-contained path: {target_lex}"
        )
    current = root.resolve()
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise UnsafeInstallPathError(
                f"Refusing to install through a symlink: {current}"
            )
    return current


def report_contained_install_path(target: Path, root: Path) -> Path | None:
    """Return the contained path, or print the refusal and return None."""
    try:
        return require_contained_install_path(target, root)
    except UnsafeInstallPathError as exc:
        print(str(exc))
        return None


def contained_scope_root(
    target: Path, *, project_root: Path, user_root: Path
) -> Path:
    """Choose the project root when target stays inside it, otherwise user_root."""
    target_lex = Path(os.path.abspath(os.fspath(target)))
    project_lex = Path(os.path.abspath(os.fspath(project_root)))
    try:
        relative = target_lex.relative_to(project_lex)
    except ValueError:
        return user_root
    if any(part in {"", ".", ".."} for part in relative.parts):
        return user_root
    return project_root
