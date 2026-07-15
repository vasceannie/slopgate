"""Typed recovery analytics for completed Slopgate result records."""

from __future__ import annotations

from .normalization import normalize_entries
from .records import NormalizationResult, NormalizedEvent, NormalizedFinding

__all__ = [
    "NormalizationResult",
    "NormalizedEvent",
    "NormalizedFinding",
    "normalize_entries",
]
