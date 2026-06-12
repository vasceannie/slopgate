"""Python file discovery helpers for lint scans."""

from __future__ import annotations

import fnmatch
import os
import subprocess
from pathlib import Path

from slopgate.lint._config import get_config
from slopgate.lint._helpers.paths import project_root, src_roots, test_roots


def _is_excluded_dir(name: str) -> bool:
    return name in get_config().exclude_dirs


def _is_excluded_file(name: str) -> bool:
    for pat in get_config().exclude_patterns:
        if fnmatch.fnmatch(name, pat):
            return True
    return False


def _scope() -> str:
    """Return the effective scan scope (all | changed | staged)."""
    return os.environ.get("QUALITY_SCOPE", get_config().default_scope)


def _git_diff_paths(*args: str) -> set[Path]:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=project_root(),
            check=False,
        )
    except FileNotFoundError:
        return set()

    root = project_root()
    return {root / item.strip() for item in result.stdout.splitlines() if item.strip()}


def _changed_files() -> set[Path]:
    """Return files changed since last commit (unstaged + staged)."""
    return _git_diff_paths("diff", "--name-only", "HEAD")


def _staged_files() -> set[Path]:
    """Return files staged for commit."""
    return _git_diff_paths("diff", "--cached", "--name-only")


def _scope_filter() -> set[Path] | None:
    """Return a set of allowed paths, or None if all files should be scanned."""
    scope = _scope()
    if scope == "changed":
        return _changed_files()
    if scope == "staged":
        return _staged_files()
    return None


def _walk_python_files(root: Path) -> list[Path]:
    """Recursively find *.py files under *root*, respecting exclusions and scope."""
    if not root.exists():
        return []
    scope_set = _scope_filter()
    resolved_scope = {p.resolve() for p in scope_set} if scope_set is not None else None
    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if not _is_excluded_dir(name)]
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            if _is_excluded_file(filename):
                continue
            full = Path(dirpath) / filename
            if resolved_scope is not None and full.resolve() not in resolved_scope:
                continue
            results.append(full)
    return sorted(results)


def _walk_roots(roots: tuple[Path, ...]) -> list[Path]:
    by_resolved: dict[Path, Path] = {}
    for root_path in roots:
        for path in _walk_python_files(root_path):
            by_resolved.setdefault(path.resolve(), path)
    return sorted(by_resolved.values())


def find_source_files() -> list[Path]:
    """Return all non-test Python source files."""
    return _walk_roots(src_roots())


def find_test_files() -> list[Path]:
    """Return all Python test files."""
    return _walk_roots(test_roots())


def find_all_python_files() -> list[Path]:
    """Return all Python files (source + test)."""
    return find_source_files() + find_test_files()
