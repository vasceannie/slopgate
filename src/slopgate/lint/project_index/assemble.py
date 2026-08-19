"""Build project-scope violations from persisted per-file facts."""

from __future__ import annotations

from collections import defaultdict

from slopgate.lint._baseline import Violation
from slopgate.lint._detectors.duplicates import build_group_violations
from slopgate.lint.project_index.models import ProjectFileSummary, ProjectIndex
from slopgate.quality.constant_index import ConstantIndex


def clone_violations(index: ProjectIndex) -> list[Violation]:
    """Group semantic-clone fingerprints across source files in the project index."""
    groups: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    for summary in index.files:
        if summary.kind != "source":
            continue
        for clone in summary.facts.semantic_clones:
            groups[clone.digest].append(
                (summary.relative_path, clone.name, clone.lineno)
            )
    return build_group_violations(
        "semantic-clone",
        groups,
        lambda digest, others: f"hash={digest}, clones: {', '.join(others[:3])}",
    )


def block_violations(index: ProjectIndex) -> list[Violation]:
    """Rebuild repeated-code-block hits from stored windows."""
    violations: list[Violation] = []
    grouped: dict[str, list[tuple[str, str, int, int]]] = defaultdict(list)
    for summary in index.files:
        if summary.kind != "source":
            continue
        for window in summary.facts.block_windows:
            grouped[window.digest].append(
                (summary.relative_path, window.scope, window.start, window.end)
            )
    for digest, members in grouped.items():
        if len(members) < 2:
            continue
        for relative, scope, start, end in members:
            violations.append(
                Violation(
                    rule="repeated-code-block",
                    relative_path=relative,
                    identifier=scope,
                    detail=f"lines {start}-{end}, block hash {digest}",
                )
            )
    return violations


def call_sequence_violations(index: ProjectIndex) -> list[Violation]:
    """Rebuild duplicate-call-sequence hits from stored sequences."""
    groups: dict[tuple[str, ...], list[tuple[str, str, int]]] = defaultdict(list)
    for summary in index.files:
        if summary.kind != "source":
            continue
        for item in summary.facts.call_sequences:
            groups[item.sequence].append(
                (summary.relative_path, item.name, item.lineno)
            )
    return build_group_violations(
        "duplicate-call-sequence",
        groups,
        lambda seq, others: (
            f"calls [{', '.join(seq[:5])}{('...' if len(seq) > 5 else '')}], "
            f"shared with {', '.join(others[:3])}"
        ),
    )


def literal_violations(index: ProjectIndex, constant_index: ConstantIndex) -> list[Violation]:
    """Rebuild repeated-literal hits from stored per-file occurrences."""
    from slopgate.lint._config import get_config
    from slopgate.lint._detectors.duplicates import (
        magic_number_violation,
        string_literal_violation,
    )

    cfg = get_config()
    numbers: dict[int | float, dict[str, set[int]]] = {}
    strings: dict[str, dict[str, set[int]]] = {}
    for summary in index.files:
        if summary.kind != "source":
            continue
        _add_numeric_facts(numbers, summary, cfg.allowed_numbers)
        _add_string_facts(strings, summary, cfg.allowed_strings)
    hits: list[Violation] = []
    for value, files_seen in numbers.items():
        if hit := magic_number_violation(value, files_seen, cfg.max_repeated_magic_numbers):
            hits.append(hit)
    for value, files_seen in strings.items():
        if hit := string_literal_violation(value, files_seen, cfg, constant_index):
            hits.append(hit)
    return hits


def _add_numeric_facts(
    numbers: dict[int | float, dict[str, set[int]]],
    summary: ProjectFileSummary,
    allowed: set[int],
) -> None:
    for item in summary.facts.magic_numbers:
        if isinstance(item.value, bool) or item.value in allowed:
            continue
        if isinstance(item.value, (int, float)):
            numbers.setdefault(item.value, {}).setdefault(summary.relative_path, set()).add(
                item.lineno
            )


def _add_string_facts(
    strings: dict[str, dict[str, set[int]]],
    summary: ProjectFileSummary,
    allowed: set[str],
) -> None:
    for item in summary.facts.string_literals:
        if isinstance(item.value, str) and item.value not in allowed:
            strings.setdefault(item.value, {}).setdefault(summary.relative_path, set()).add(
                item.lineno
            )
