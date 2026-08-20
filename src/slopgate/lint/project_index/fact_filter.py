"""Fact-type filter for incremental file-fact extraction."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

_ACTIVE_FACT_TYPES: ContextVar[frozenset[str] | None] = ContextVar(
    "slopgate_index_fact_types", default=None
)


@contextmanager
def fact_type_filter(kinds: frozenset[str] | None) -> Generator[None, None, None]:
    """Apply a fact-type allowlist for one index refresh, then restore the prior filter."""
    token = _ACTIVE_FACT_TYPES.set(kinds)
    try:
        yield
    finally:
        _ACTIVE_FACT_TYPES.reset(token)


def wanted_fact_type(fact_type: str) -> bool:
    """Return True when *fact_type* should be extracted for this index pass."""
    kinds = _ACTIVE_FACT_TYPES.get()
    return kinds is None or fact_type in kinds
