"""Name coverage for dirty inventory helper."""

from __future__ import annotations

from slopgate.lint.project_index.dirty import collect_dirty_and_deleted, untracked_python_paths


def test_collect_dirty_and_deleted_name() -> None:
    assert (collect_dirty_and_deleted.__name__, untracked_python_paths.__name__) == (
        "collect_dirty_and_deleted",
        "untracked_python_paths",
    )
