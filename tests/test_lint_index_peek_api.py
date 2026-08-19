"""Contract for cheap lint index peek readiness."""

from __future__ import annotations

from pathlib import Path

from slopgate.lint.project_index.peek import IndexPeek, peek_index


def test_peek_index_not_ready_on_fresh_root(tmp_path: Path) -> None:
    peek = peek_index(tmp_path, ())
    assert (isinstance(peek, IndexPeek), peek.ready) == (True, False)
