"""Deterministic completed-result deduplication."""

from __future__ import annotations

from dataclasses import dataclass

from slopgate._types import ObjectDict


@dataclass(frozen=True, slots=True)
class _DeduplicationResult:
    """Input-indexed result records after evaluation-ID deduplication."""

    entries: tuple[tuple[int, ObjectDict], ...]
    duplicate_records_removed: int


def dedupe_entries(entries: list[ObjectDict]) -> _DeduplicationResult:
    """Keep the first occurrence of each explicit evaluation ID."""
    seen_evaluation_ids: set[str] = set()
    deduplicated: list[tuple[int, ObjectDict]] = []
    duplicate_records_removed = 0
    for index, entry in enumerate(entries):
        evaluation_id = entry.get("evaluation_id")
        if isinstance(evaluation_id, str) and evaluation_id:
            if evaluation_id in seen_evaluation_ids:
                duplicate_records_removed += 1
                continue
            seen_evaluation_ids.add(evaluation_id)
        deduplicated.append((index, entry))
    return _DeduplicationResult(
        entries=tuple(deduplicated),
        duplicate_records_removed=duplicate_records_removed,
    )
