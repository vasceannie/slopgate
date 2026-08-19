"""Hypothesis references for project index assemble and facts."""

from __future__ import annotations

from hypothesis import given, strategies

from slopgate.lint.project_index.assemble import literal_violations
from slopgate.lint.project_index.dirty import collect_dirty_and_deleted, untracked_python_paths
from slopgate.lint.project_index.integrity_facts import (
    attach_integrity_facts,
    integrity_index_from_project,
)
from slopgate.lint.project_index.integrity_store import load_integrity_index
from slopgate.lint.project_index.peek import peek_index
from slopgate.lint.project_index.persist import build_persisted_index
from slopgate.lint.project_index.refresh import refresh_index_summaries
from slopgate.lint.project_index.summarize import dirty_relative_paths


@given(strategies.integers(min_value=0, max_value=2))
def test_index_fact_helper_names(value: int) -> None:
    assert (
        literal_violations.__name__,
        collect_dirty_and_deleted.__name__,
        untracked_python_paths.__name__,
        attach_integrity_facts.__name__,
        integrity_index_from_project.__name__,
        peek_index.__name__,
        build_persisted_index.__name__,
        refresh_index_summaries.__name__,
        dirty_relative_paths.__name__,
        load_integrity_index.__name__,
        value,
    )[-1] == value
