"""Contracts for deferred integrity collector specs."""

from __future__ import annotations

from slopgate.lint._collector_groups.integrity_specs import (
    lazy_integrity_index,
    touched_integrity_collector_specs,
)


def test_touched_integrity_collector_specs_are_named() -> None:
    specs = touched_integrity_collector_specs([])
    assert specs[0].collector_id == "weak-test-assertion"


def test_lazy_integrity_index_is_callable() -> None:
    assert callable(lazy_integrity_index([], []))
