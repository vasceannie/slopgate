"""Trust checks for repository-local lint cache files."""

from __future__ import annotations

from pathlib import Path

from slopgate.config._repo import git_output
from slopgate.constants import LINT_CACHE_DIRNAME


def cache_path_is_trusted(project_root: Path, cache_path: Path) -> bool:
    """Return whether a cache path is untracked, local, and free of symlinks."""
    root = project_root.resolve()
    candidate = cache_path.absolute()
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return False
    cache_parts = Path(LINT_CACHE_DIRNAME).parts
    if relative.parts[: len(cache_parts)] != cache_parts:
        return False
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            return False
    tracked = git_output(
        ["git", "-C", str(root), "ls-files", "--cached", "--", LINT_CACHE_DIRNAME],
        cwd=root,
    )
    return tracked == ""
