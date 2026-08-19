"""Name coverage for persisted index build."""

from __future__ import annotations

from slopgate.lint.project_index.persist import build_persisted_index
from slopgate.lint.project_index.refresh import refresh_index_summaries


def test_persist_and_refresh_names() -> None:
    assert (build_persisted_index.__name__, refresh_index_summaries.__name__) == (
        "build_persisted_index",
        "refresh_index_summaries",
    )
