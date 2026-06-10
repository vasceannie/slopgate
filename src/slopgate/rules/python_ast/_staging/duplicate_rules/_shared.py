"""Shared helpers for duplicate-code staging rules."""

from __future__ import annotations

from slopgate.models import RuleFinding

MIN_BLOCK_SIZE = 3


def finding_count(finding: RuleFinding) -> int:
    count = finding.metadata.get("count")
    return count if isinstance(count, int) else 0
