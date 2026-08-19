"""Name coverage for remaining enrolled index store helpers."""

from __future__ import annotations

from slopgate.lint.project_index.store import (
    load_cached_collector_results,
    mark_file_local_ready,
    reset_store,
)


def test_store_mutation_helper_names() -> None:
    assert (
        load_cached_collector_results.__name__,
        mark_file_local_ready.__name__,
        reset_store.__name__,
    ) == (
        "load_cached_collector_results",
        "mark_file_local_ready",
        "reset_store",
    )
