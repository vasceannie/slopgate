"""Working-tree dirty, untracked, and deleted Python paths for incremental lint."""

from __future__ import annotations

from pathlib import Path

from slopgate.config._repo import GIT_BIN, git_output
from slopgate.constants import LANGUAGE_BY_SUFFIX


def collect_dirty_and_deleted(
    root: Path, inventory: tuple[Path, ...]
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    """Return dirty (modified/untracked) and deleted inventory paths."""
    inventory_by_relative = {
        path.resolve().relative_to(root).as_posix(): path.resolve()
        for path in inventory
        if path.resolve().is_relative_to(root)
    }
    if not _is_git_work_tree(root):
        return tuple(sorted(inventory_by_relative.values())), ()
    modified_relatives = _git_path_set(root, "diff", "--name-only", "HEAD")
    untracked_relatives = _git_path_set(
        root, "ls-files", "--others", "--exclude-standard"
    )
    deleted_relatives = _git_path_set(
        root, "diff", "--name-only", "--diff-filter=D", "HEAD"
    )
    if (
        modified_relatives is None
        or untracked_relatives is None
        or deleted_relatives is None
    ):
        return tuple(sorted(inventory_by_relative.values())), ()
    dirty_relatives = modified_relatives | untracked_relatives
    dirty = tuple(
        sorted(
            inventory_by_relative[relative]
            for relative in dirty_relatives
            if relative in inventory_by_relative
        )
    )
    deleted = tuple(
        sorted(
            (root / relative).resolve()
            for relative in deleted_relatives
            if Path(relative).suffix == next(iter(LANGUAGE_BY_SUFFIX))
        )
    )
    return dirty, deleted


def untracked_python_paths(root: Path) -> tuple[Path, ...]:
    """Return untracked Python files under *root* according to git."""
    suffix = next(iter(LANGUAGE_BY_SUFFIX))
    relatives = _git_path_set(root, "ls-files", "--others", "--exclude-standard")
    if relatives is None:
        return ()
    return tuple(
        sorted(
            (root / relative).resolve()
            for relative in relatives
            if relative.endswith(suffix) and (root / relative).is_file()
        )
    )


def _is_git_work_tree(root: Path) -> bool:
    output = git_output(
        [GIT_BIN, "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        cwd=root,
    )
    return output == "true"


def _git_path_set(root: Path, *args: str) -> set[str] | None:
    output = git_output([GIT_BIN, "-C", str(root), *args], cwd=root)
    if output is None:
        return None
    return {line.strip() for line in output.splitlines() if line.strip()}
