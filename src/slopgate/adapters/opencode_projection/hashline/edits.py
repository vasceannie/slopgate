"""Validation and application of OMO hashline edit operations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, NamedTuple, TypeAlias, cast

from slopgate._types import object_dict, string_value
from slopgate.constants import REPLACE
from slopgate.util import logger

from ..constants import (
    DIFF_PLUS_PATTERN,
    HASHLINE_PREFIX_PATTERN,
    HASHLINE_REF_EXTRACT_PATTERN,
    HASHLINE_REF_PATTERN,
)
from .hash import line_hash

HashlineFailure: TypeAlias = Literal["empty_insertion", "stale_hash_anchor"]


class HashlineEditResult(NamedTuple):
    """Projected content and precise failure reason."""

    content: str | None
    failure: HashlineFailure | None


@dataclass(frozen=True, slots=True)
class _HashlineEdit:
    operation: str
    position: str | None
    end: str | None
    lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ResolvedEdit:
    edit: _HashlineEdit
    start: int
    end: int
    sort_line: int


def _normalize_anchor(value: object) -> str | None:
    logger.debug("Hashline anchor normalization requested")
    original = string_value(value)
    if original is None:
        return None
    trimmed = original.strip()
    trimmed = re.sub(r"^(?:>>>|[+-])\s*", "", trimmed)
    trimmed = re.sub(r"\s*#\s*", "#", trimmed)
    trimmed = re.sub(r"\|.*$", "", trimmed).strip()
    if HASHLINE_REF_PATTERN.fullmatch(trimmed):
        return trimmed
    extracted = HASHLINE_REF_EXTRACT_PATTERN.search(trimmed)
    return extracted.group(1) if extracted is not None else original.strip()


def _parse_anchor(value: str) -> tuple[int, str] | None:
    logger.debug("Hashline anchor parsing requested")
    match = HASHLINE_REF_PATTERN.fullmatch(value)
    if match is None:
        return None
    return int(match.group(1)), match.group(2)


def _normalize_lines(value: object) -> tuple[str, ...] | None:
    logger.debug("Hashline replacement normalization requested")
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(value.split("\n"))
    if not isinstance(value, list):
        return None
    lines: list[str] = []
    for line in cast(list[object], value):
        if not isinstance(line, str):
            return None
        lines.append(line)
    return tuple(lines)


def _parse_edit(value: object) -> _HashlineEdit | None:
    logger.debug("Hashline edit parsing requested")
    raw = object_dict(value)
    operation = string_value(raw.get("op"))
    if operation not in {REPLACE, "append", "prepend"}:
        return None
    if "lines" not in raw:
        return None
    lines = _normalize_lines(raw.get("lines"))
    if lines is None:
        return None
    position = _normalize_anchor(raw.get("pos"))
    end = _normalize_anchor(raw.get("end"))
    position = position or end
    if operation == REPLACE and position is None:
        return None
    return _HashlineEdit(operation, position, end, lines)


def _prepare_edits(value: object) -> list[_HashlineEdit] | None:
    logger.debug("Hashline edit preparation requested")
    if not isinstance(value, list):
        return None
    edits: list[_HashlineEdit] = []
    seen: set[tuple[object, ...]] = set()
    for item in cast(list[object], value):
        edit = _parse_edit(item)
        if edit is None:
            return None
        key = (edit.operation, edit.position, edit.end, edit.lines)
        if key in seen:
            continue
        seen.add(key)
        edits.append(edit)
    return edits


def _line_number(
    anchor: str, lines: list[str]
) -> tuple[int | None, HashlineFailure | None]:
    logger.debug("Hashline line reference validation requested", anchor=anchor)
    parsed = _parse_anchor(anchor)
    if parsed is None:
        return None, None
    line, expected_hash = parsed
    if not 1 <= line <= len(lines):
        return None, "stale_hash_anchor"
    actual = lines[line - 1]
    compatible = expected_hash in {
        line_hash(line, actual),
        line_hash(line, actual, legacy=True),
    }
    return (line, None) if compatible else (None, "stale_hash_anchor")


def _has_overlapping_ranges(resolved: list[_ResolvedEdit]) -> bool:
    logger.debug("Hashline range overlap check requested", edit_count=len(resolved))
    ranges = sorted(
        (item.start, item.end)
        for item in resolved
        if item.edit.operation == REPLACE and item.edit.end is not None
    )
    return any(current[0] <= previous[1] for previous, current in zip(ranges, ranges[1:]))


def _resolve_edits(
    edits: list[_HashlineEdit], lines: list[str]
) -> tuple[list[_ResolvedEdit] | None, HashlineFailure | None]:
    logger.debug("Hashline edit resolution requested", edit_count=len(edits))
    resolved: list[_ResolvedEdit] = []
    precedence = {REPLACE: 0, "append": 1, "prepend": 2}
    for edit in edits:
        if edit.position is None:
            resolved.append(_ResolvedEdit(edit, 0, 0, 0))
            continue
        start, failure = _line_number(edit.position, lines)
        if start is None:
            return None, failure
        end = start
        if edit.operation == REPLACE and edit.end is not None:
            end, failure = _line_number(edit.end, lines)
            if end is None:
                return None, failure
            if end < start:
                return None, None
        sort_line = end if edit.operation == REPLACE else start
        resolved.append(_ResolvedEdit(edit, start, end, sort_line))
    resolved.sort(
        key=lambda item: (-item.sort_line, precedence.get(item.edit.operation, 3))
    )
    if _has_overlapping_ranges(resolved):
        return None, None
    return resolved, None


def _new_lines(lines: tuple[str, ...]) -> list[str]:
    logger.debug("Hashline replacement lines requested", line_count=len(lines))
    non_empty = [line for line in lines if line]
    hash_count = sum(1 for line in non_empty if HASHLINE_PREFIX_PATTERN.match(line))
    plus_count = sum(1 for line in non_empty if DIFF_PLUS_PATTERN.match(line))
    if non_empty and hash_count * 2 >= len(non_empty):
        return [HASHLINE_PREFIX_PATTERN.sub("", line) for line in lines]
    if non_empty and plus_count * 2 >= len(non_empty):
        return [DIFF_PLUS_PATTERN.sub("", line) for line in lines]
    return list(lines)


def _strip_insert_echo(anchor: str, lines: list[str], *, before: bool) -> list[str]:
    logger.debug("Hashline insert echo check requested", before=before)
    if not lines:
        return lines
    if before and len(lines) <= 1:
        return lines
    candidate = lines[-1] if before else lines[0]
    compact_candidate = re.sub(r"\s+", "", candidate)
    compact_anchor = re.sub(r"\s+", "", anchor)
    if candidate == anchor or compact_candidate == compact_anchor:
        return lines[:-1] if before else lines[1:]
    return lines


def _restore_pair(template: str, line: str) -> str:
    logger.debug("Hashline indentation pair requested")
    if not line or not template[:1].isspace() or line[:1].isspace():
        return line
    if template.strip() == line.strip():
        return line
    indent = template[: len(template) - len(template.lstrip())]
    return indent + line


def _restore_indent(original: list[str], replacement: list[str]) -> list[str]:
    logger.debug(
        "Hashline indentation restoration requested", line_count=len(replacement)
    )
    if not replacement:
        return replacement
    if len(original) == len(replacement):
        return [
            _restore_pair(template, line)
            for template, line in zip(original, replacement)
        ]
    if not original:
        return replacement
    return [_restore_pair(original[0], replacement[0]), *replacement[1:]]


def _apply_edit(lines: list[str], resolved: _ResolvedEdit) -> bool:
    logger.debug(
        "Hashline edit application requested", operation=resolved.edit.operation
    )
    edit = resolved.edit
    if edit.operation == REPLACE:
        original = lines[resolved.start - 1 : resolved.end]
        replacement = _new_lines(edit.lines)
        lines[resolved.start - 1 : resolved.end] = _restore_indent(
            original, replacement
        )
        return True
    replacement = _new_lines(edit.lines)
    if edit.position is not None:
        anchor = lines[resolved.start - 1]
        replacement = _strip_insert_echo(
            anchor, replacement, before=edit.operation == "prepend"
        )
        if not replacement:
            return False
        insertion = (
            resolved.start - 1 if edit.operation == "prepend" else resolved.start
        )
    else:
        insertion = 0 if edit.operation == "prepend" else len(lines)
    if not replacement:
        return False
    lines[insertion:insertion] = replacement
    return True


def _canonicalize(content: str) -> tuple[list[str], str, bool, str]:
    logger.debug(
        "Hashline file canonicalization requested", content_length=len(content)
    )
    had_bom = content.startswith("\ufeff")
    without_bom = content[1:] if had_bom else content
    crlf_index = without_bom.find("\r\n")
    if crlf_index != -1:
        line_ending = "\r\n"
    else:
        line_ending = "\n"
    normalized = without_bom.replace("\r\n", "\n").replace("\r", "\n")
    lines = [] if not normalized else normalized.split("\n")
    return lines, line_ending, had_bom, normalized


def _restore_content(lines: list[str], line_ending: str, had_bom: bool) -> str:
    logger.debug("Hashline file restoration requested", line_count=len(lines))
    content = "\n".join(lines)
    if line_ending != "\n":
        content = content.replace("\n", line_ending)
    return f"\ufeff{content}" if had_bom else content


def project_hashline_edits(content: str, raw_edits: object) -> HashlineEditResult:
    """Project OMO hashline edits with a precise validation failure reason."""
    logger.debug("Hashline edit projection requested", content_length=len(content))
    edits = _prepare_edits(raw_edits)
    if edits is None:
        return HashlineEditResult(None, None)
    lines, line_ending, had_bom, canonical = _canonicalize(content)
    resolved, failure = _resolve_edits(edits, lines)
    if resolved is None:
        return HashlineEditResult(None, failure)
    for edit in resolved:
        if not _apply_edit(lines, edit):
            return HashlineEditResult(None, "empty_insertion")
    projected = "\n".join(lines)
    if projected == canonical:
        return HashlineEditResult(content, None)
    return HashlineEditResult(_restore_content(lines, line_ending, had_bom), None)


def apply_hashline_edits(content: str, raw_edits: object) -> str | None:
    """Apply OMO hashline edits, returning ``None`` when validation fails."""
    logger.debug("Public hashline edit application requested")
    return project_hashline_edits(content, raw_edits).content
