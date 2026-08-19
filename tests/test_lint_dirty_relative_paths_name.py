"""Name coverage for dirty_relative_paths."""

from __future__ import annotations

from slopgate.lint.project_index.summarize import dirty_relative_paths


def test_dirty_relative_paths_name() -> None:
    assert dirty_relative_paths.__name__ == "dirty_relative_paths"
