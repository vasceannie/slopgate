"""Local enrichment helpers for quality-related rule IDs."""

from __future__ import annotations

from slopgate.enrichment.quality_enrichers._magic_numbers import enrich_magic_numbers
from slopgate.enrichment.quality_enrichers._paths import enrich_hardcoded_paths

__all__ = ["enrich_hardcoded_paths", "enrich_magic_numbers"]
