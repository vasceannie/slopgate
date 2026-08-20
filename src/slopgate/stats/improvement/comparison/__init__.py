"""Guarded baseline-vs-candidate comparison by provenance fingerprint.

Comparisons never mix legacy rows, always emit facet breakdowns, and
suppress the headline aggregate whenever a dimension other than the selected
fingerprint varies within or across the selected cohorts.
"""

from __future__ import annotations

from .evaluate import apply_cohort_filters, build_comparison
from .selectors import (
    COMPARISON_DIMENSIONS,
    ComparisonRequest,
    ComparisonSpec,
    parse_cohort_filters,
    resolve_comparison,
)

__all__ = [
    "COMPARISON_DIMENSIONS",
    "ComparisonRequest",
    "ComparisonSpec",
    "apply_cohort_filters",
    "build_comparison",
    "parse_cohort_filters",
    "resolve_comparison",
]
