"""Detectors for code duplication."""

from __future__ import annotations

import ast
from collections.abc import Set
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from slopgate.constants import METADATA_PATH
from slopgate.lint._baseline import Violation
from slopgate.lint._config import get_config
from slopgate.lint._helpers import ParsedFile, ensure_parsed, find_source_files
from slopgate.quality.constant_index import (
    ConstantIndex,
    StringConstantMatch,
    build_project_constant_index,
    set_session_constant_index,
    suggest_constant_name,
)

from .semantic import is_docstring_node

if TYPE_CHECKING:
    from slopgate.lint._config import QualityConfig

_MAX_EXISTING_LOCATION_PREVIEW = 12
_LiteralValue = TypeVar("_LiteralValue", int, float, str)


def _record_occurrence(
    index: dict[_LiteralValue, dict[str, set[int]]],
    value: _LiteralValue,
    rel_path: str,
    lineno: int,
) -> None:
    by_file = index.setdefault(value, {})
    by_file.setdefault(rel_path, set()).add(lineno)


def collect_literals(
    parsed: list[ParsedFile], allowed_nums: Set[int | float], allowed_strs: set[str]
) -> tuple[dict[int | float, dict[str, set[int]]], dict[str, dict[str, set[int]]]]:
    """Walk ASTs and count non-allowed literal occurrences per file."""
    num_counts: dict[int | float, dict[str, set[int]]] = {}
    str_counts: dict[str, dict[str, set[int]]] = {}
    for pf in parsed:
        for node in ast.walk(pf.tree):
            if not isinstance(node, ast.Constant):
                continue
            if isinstance(node.value, bool) or is_docstring_node(node, pf.parent_map):
                continue
            val = node.value
            if isinstance(val, (int, float)) and val not in allowed_nums:
                _record_occurrence(num_counts, val, pf.rel, node.lineno)
            elif (
                isinstance(val, str)
                and val not in allowed_strs
                and is_semantic_string_literal(val)
            ):
                _record_occurrence(str_counts, val, pf.rel, node.lineno)
    return (num_counts, str_counts)


def is_semantic_string_literal(value: str) -> bool:
    """Return True when a string literal is worth extracting to a named owner."""
    stripped = value.strip()
    if not stripped:
        return False
    return any((char.isalnum() for char in stripped))


def constant_location(
    constant_match: StringConstantMatch, project_root: Path
) -> tuple[str, int]:
    path = constant_match.path
    try:
        path = constant_match.path.relative_to(project_root)
    except ValueError:
        pass
    return (path.as_posix(), constant_match.lineno)


def string_literal_metadata(
    value: str, constant_index: ConstantIndex, project_root: Path
) -> tuple[dict[str, object], str]:
    constant_match = constant_index.find_string_constant(value)
    if constant_match is None:
        candidate = suggest_constant_name(value)
        return ({"candidate_constant_name": candidate}, f"; consider `{candidate}`")
    relative, lineno = constant_location(constant_match, project_root)
    already_defined: dict[str, object] = {
        "name": constant_match.name,
        METADATA_PATH: relative,
        "line": lineno,
    }
    guidance = "do not duplicate it or hide the literal with string fragments"
    suffix = (
        f"; import existing constant {constant_match.name} "
        f"from {relative}:{lineno}; {guidance}"
    )
    return ({"already_defined": already_defined}, suffix)


def _collect_existing_locations(
    occurrences: dict[str, set[int]],
) -> tuple[list[str], int]:
    locations: list[str] = []
    total = 0
    for rel_path in sorted(occurrences):
        for lineno in sorted(occurrences[rel_path]):
            total += 1
            if len(locations) < _MAX_EXISTING_LOCATION_PREVIEW:
                locations.append(f"{rel_path}:{lineno}")
    return (locations, total - len(locations))


def _existing_location_detail_suffix(occurrences: dict[str, set[int]]) -> str:
    locations, remaining = _collect_existing_locations(occurrences)
    if not locations:
        return ""
    location_text = ", ".join(locations)
    if remaining > 0:
        location_text += f", ... +{remaining} more"
    return f"; locations: {location_text}"


def _existing_location_metadata(occurrences: dict[str, set[int]]) -> dict[str, object]:
    locations, remaining = _collect_existing_locations(occurrences)
    metadata: dict[str, object] = {"existing_locations": locations}
    if remaining > 0:
        metadata["existing_locations_more"] = remaining
    return metadata


def magic_number_violation(
    value: int | float, occurrences: dict[str, set[int]], max_files: int
) -> Violation | None:
    files_seen = set(occurrences)
    if len(files_seen) <= max_files:
        return None
    return Violation(
        rule="repeated-magic-number",
        relative_path="<project>",
        identifier=repr(value),
        detail=(
            f"appears in {len(files_seen)} files (max: {max_files})"
            f"{_existing_location_detail_suffix(occurrences)}"
        ),
        metadata=_existing_location_metadata(occurrences),
    )


def string_literal_violation(
    value: str,
    occurrences: dict[str, set[int]],
    cfg: "QualityConfig",
    constant_index: ConstantIndex,
) -> Violation | None:
    max_files = cfg.max_repeated_string_literals
    files_seen = set(occurrences)
    if len(files_seen) <= max_files:
        return None
    metadata = _existing_location_metadata(occurrences)
    constant_metadata, detail_suffix = string_literal_metadata(
        value, constant_index, cfg.project_root
    )
    metadata.update(constant_metadata)
    detail = (
        f"appears in {len(files_seen)} files (max: {max_files})"
        f"{_existing_location_detail_suffix(occurrences)}"
        f"{detail_suffix}"
    )
    return Violation(
        rule="repeated-string-literal",
        relative_path="<project>",
        identifier=repr(value)[:40],
        detail=detail,
        metadata=metadata,
    )


def detect_repeated_literals(
    files: list[Path] | list[ParsedFile] | None = None,
    *,
    constant_index: ConstantIndex | None = None,
) -> list[Violation]:
    """Flag magic numbers and string literals used excessively."""
    cfg = get_config()
    parsed = ensure_parsed(files, fallback=find_source_files())
    if constant_index is None:
        constant_index = build_project_constant_index(cfg.project_root)
    set_session_constant_index(constant_index)
    num_counts, str_counts = collect_literals(
        parsed, cfg.allowed_numbers, cfg.allowed_strings
    )
    violations: list[Violation] = []
    for value, files_seen in num_counts.items():
        violation = magic_number_violation(
            value, files_seen, cfg.max_repeated_magic_numbers
        )
        if violation is not None:
            violations.append(violation)
    for value, files_seen in str_counts.items():
        violation = string_literal_violation(value, files_seen, cfg, constant_index)
        if violation is not None:
            violations.append(violation)
    return violations
