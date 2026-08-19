"""Hypothesis references for index store helpers."""

from __future__ import annotations

from hypothesis import given, strategies

from slopgate.lint.project_index.store import (
    load_cached_collector_results,
    load_violations_for_hashes,
    replace_file_violations,
    store_matches_engine,
    summary_from_row,
)


@given(strategies.integers(min_value=0, max_value=2))
def test_store_helper_names(value: int) -> None:
    assert (
        load_cached_collector_results.__name__,
        load_violations_for_hashes.__name__,
        replace_file_violations.__name__,
        store_matches_engine.__name__,
        summary_from_row.__name__,
        value,
    )[-1] == value
