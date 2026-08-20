"""Hook activity log analysis."""

from __future__ import annotations

__all__ = [
    "analyze",
    "load_entries",
    "parse_timestamp",
    "print_report",
    "run_stats",
]

from ._analysis import analyze
from ._load import load_entries, parse_timestamp
from ._report import print_report, run_stats
from .improvement import (
    ComparisonRequest,
    ComparisonSpec,
    build_improvement,
    resolve_comparison,
)

__all__ = [
    "ComparisonRequest",
    "ComparisonSpec",
    "analyze",
    "build_improvement",
    "load_entries",
    "parse_timestamp",
    "print_report",
    "resolve_comparison",
    "run_stats",
]
