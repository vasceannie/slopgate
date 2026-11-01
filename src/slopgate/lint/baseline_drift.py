"""Match known lint ids to current ids when only ``file:line`` numbers moved."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from slopgate.lint._baseline import Violation

# Project-wide detectors render line numbers in exactly two places inside the
# detail field: the ``; locations: a.py:11, b.py:27`` list and the
# ``import existing constant NAME from pkg/const.py:12`` clause that names the
# constant already owning a repeated literal. Everything else (rule, path,
# identifier, ``max: N``, and any later prose) keeps its exact text, so values
# such as ``https://host:443`` or ``pkg.mod:12`` keep their identity.
LOCATIONS_MARKER = "; locations: "
DETAIL_CLAUSE_SEPARATOR = "; "
LOCATION_ENTRY_RE = re.compile(r"([^\s,;]+):\d+(?=,|$)")
CONSTANT_SOURCE_RE = re.compile(
    r"(import existing constant [^;]*? from )([^\s,;]+):\d+"
)


def _drop_location_lines(segment: str) -> str:
    """Strip ``:<line>`` from each entry of a rendered locations list."""
    return LOCATION_ENTRY_RE.sub(r"\1", segment)


def _drop_constant_source_line(clause: str) -> str:
    """Strip ``:<line>`` from a rendered constant-source reference."""
    return CONSTANT_SOURCE_RE.sub(r"\1\2", clause)


def line_insensitive_id(stable_id: str) -> str:
    """Drop rendered location lines so line shifts keep the same identity.

    A known id and a current id that agree on rule, path, identifier, and
    thresholds but differ only in the ``; locations:`` list or the constant
    source line are the same debt at a new line. Ids without a rendered
    locations marker, and any text outside those two segments, pass through
    unchanged.
    """
    head, marker, tail = stable_id.partition(LOCATIONS_MARKER)
    if not marker:
        return stable_id
    segment, separator, remainder = tail.partition(DETAIL_CLAUSE_SEPARATOR)
    stripped_segment = _drop_location_lines(segment)
    stripped_remainder = _drop_constant_source_line(remainder)
    return f"{head}{marker}{stripped_segment}{separator}{stripped_remainder}"


def current_ids_by_rule(
    collectors: list[tuple[str, list[Violation]]],
) -> dict[str, set[str]]:
    """Collect the current scan's stable ids per rule."""
    current: dict[str, set[str]] = {}
    for rule, violations in collectors:
        current.setdefault(rule, set()).update(
            violation.stable_id for violation in violations
        )
    return current


def _group_by_line_insensitive_id(stable_ids: set[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for stable_id in sorted(stable_ids):
        groups.setdefault(line_insensitive_id(stable_id), []).append(stable_id)
    return groups


def _reconcile_rule_ids(known: set[str], current: set[str]) -> set[str]:
    """Swap each moved known id for its current id when the pairing is unique.

    Exact matches always win. A moved id is only adopted when exactly one
    unmatched known id and one unmatched current id share the line-free form;
    ambiguous groups keep the known ids so new debt still surfaces.
    """
    reconciled = known & current
    unmatched_current = _group_by_line_insensitive_id(current - known)
    for key, moved in _group_by_line_insensitive_id(known - current).items():
        candidates = unmatched_current.get(key, [])
        if len(moved) == 1 and len(candidates) == 1:
            reconciled.add(candidates[0])
        else:
            reconciled.update(moved)
    return reconciled


def reconcile_line_drift(
    known: dict[str, set[str]], current: dict[str, set[str]]
) -> dict[str, set[str]]:
    """Return *known* with line-shifted ids replaced by their current ids."""
    return {
        rule: _reconcile_rule_ids(ids, current.get(rule, set()))
        for rule, ids in known.items()
    }


__all__ = ["current_ids_by_rule", "line_insensitive_id", "reconcile_line_drift"]
