"""Pure OpenCode v2.2.5 patch parsing and unformatted text application."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from slopgate._types import ObjectMapping, string_value
from slopgate.util import logger

from .exact import _normalize_text
from .models import PatchOperation, PatchSection, Projection

_HEADERS: tuple[tuple[str, PatchOperation], ...] = (
    ("*** Add File: ", "add"),
    ("*** Update File: ", "update"),
    ("*** Delete File: ", "delete"),
)
_HEREDOC = re.compile(r"^(?:cat\s+)?<<(['\"]?)(\w+)\1\s*\n([\s\S]*?)\n\2\s*$")


@dataclass(slots=True)
class _UpdateChunk:
    old: list[str]
    new: list[str]
    anchor: str | None = None
    eof: bool = False


def _patch_lines(text: str) -> list[str]:
    logger.debug("OpenCode native patch envelope decoded")
    wrapper = _HEREDOC.fullmatch(text.strip())
    lines = (wrapper.group(3) if wrapper else text.strip()).split("\n")
    lines = [line.removesuffix("\r") for line in lines]
    if (
        len(lines) > 2
        and lines[1].strip().startswith("*** Environment ID:")
        and lines[1].split(":", 1)[1].strip()
    ):
        lines.pop(1)
    return lines


def invalid_patch_projection(operation: PatchOperation, relative: str) -> Projection:
    """Return the invalid projection for an unapplicable patch section."""
    logger.debug("OpenCode patch section rejected", operation=operation, path=relative)
    if operation == "update":
        return Projection(
            "invalid", reason="update_hunk_mismatch", target_path=relative
        )
    return Projection("invalid")


def _move_target(
    line: str,
    active: tuple[PatchOperation, str, str | None] | None,
    has_body: bool,
) -> tuple[PatchOperation, str, str | None] | None:
    logger.debug("OpenCode patch move target parsed")
    destination = line.rstrip().removeprefix("*** Move to:").strip()
    if active is None or active[0] != "update" or has_body:
        return None
    if not destination or active[2] is not None:
        return None
    return active[0], active[1], destination


def _section_header(
    line: str, active: tuple[PatchOperation, str, str | None] | None
) -> tuple[PatchOperation, str] | None:
    logger.debug("OpenCode patch section header checked")
    # Inside an update the host trims only line ends: an indented header is context.
    in_update = active is not None and active[0] == "update"
    candidate = line.rstrip() if in_update else line.strip()
    for prefix, kind in _HEADERS:
        if candidate.startswith(prefix):
            return kind, candidate.removeprefix(prefix).strip()
    return None


def _consume_patch_line(
    line: str,
    active: tuple[PatchOperation, str, str | None] | None,
    body: list[str],
    sections: list[PatchSection],
) -> tuple[tuple[PatchOperation, str, str | None] | None, bool] | None:
    logger.debug("OpenCode patch line consumed", has_active_section=active is not None)
    if (
        active is not None
        and active[0] == "update"
        and not body
        and line.rstrip() == "*** End of File"
    ):
        return active, False
    if line.rstrip() == "*** Move to:" or line.rstrip().startswith("*** Move to: "):
        moved = _move_target(line, active, bool(body))
        return (moved, False) if moved is not None else None
    header = _section_header(line, active)
    if header is None:
        if active is None:
            return None
        body.append(line)
        return active, False
    if active is not None:
        sections.append(PatchSection(active[0], active[1], tuple(body), active[2]))
    return (header[0], header[1], None), True


def parse_patch(text: str) -> tuple[PatchSection, ...] | None:
    """Parse the documented OpenCode patch envelope into file sections."""
    logger.debug("OpenCode patch parsed", text_length=len(text))
    lines = _patch_lines(text)
    valid_envelope = (
        len(lines) >= 3
        and lines[0].strip() == "*** Begin Patch"
        and lines[-1].strip() == "*** End Patch"
    )
    if not valid_envelope:
        return None
    sections: list[PatchSection] = []
    active: tuple[PatchOperation, str, str | None] | None = None
    body: list[str] = []
    for line in lines[1:-1]:
        consumed = _consume_patch_line(line, active, body, sections)
        if consumed is None:
            return None
        active, reset_body = consumed
        if reset_body:
            body = []
    if active is None:
        return None
    sections.append(PatchSection(active[0], active[1], tuple(body), active[2]))
    return tuple(sections)


def _chunk_marker(chunks: list[_UpdateChunk], marker: str) -> bool | None:
    logger.debug("OpenCode patch chunk marker parsed")
    if marker == "*** End of File":
        if chunks:
            if not chunks[-1].old and not chunks[-1].new:
                return False
            chunks[-1].eof = True
        return True
    if marker == "@@" or marker.startswith("@@ "):
        if chunks and not chunks[-1].old and not chunks[-1].new:
            return False
        chunks.append(_UpdateChunk([], [], marker[3:] if marker != "@@" else None))
        return True
    return None


def _append_chunk_line(chunk: _UpdateChunk, line: str) -> bool:
    logger.debug("OpenCode patch body line parsed")
    if not line or line.startswith(" "):
        value = line[1:] if line else ""
        chunk.old.append(value)
        chunk.new.append(value)
    elif line.startswith("+"):
        chunk.new.append(line[1:])
    elif line.startswith("-"):
        chunk.old.append(line[1:])
    else:
        return False
    return True


def _parse_update_chunks(lines: tuple[str, ...]) -> tuple[_UpdateChunk, ...] | None:
    logger.debug("OpenCode update chunks parsed", lines=len(lines))
    chunks: list[_UpdateChunk] = []
    for line in lines:
        marker = line.rstrip()
        handled = _chunk_marker(chunks, marker)
        if handled is False:
            return None
        if handled:
            continue
        if chunks and chunks[-1].eof:
            if marker:
                return None
            continue
        if not chunks:
            chunks.append(_UpdateChunk([], []))
        if not _append_chunk_line(chunks[-1], line):
            return None
    if not chunks or (not chunks[-1].old and not chunks[-1].new):
        return None
    return tuple(chunks)


def _seek_line_match(
    source: list[str], expected: list[str], start: int, eof: bool = False
) -> int | None:
    """Find the first forward line-block match using native opencode comparators."""
    logger.debug(
        "OpenCode update match requested",
        source_lines=len(source),
        expected_lines=len(expected),
        start_line=start,
    )
    width = len(expected)
    if not width:
        return None
    end = len(source) - width
    offsets = range(max(start, end), end + 1) if eof else range(start, end + 1)
    comparators: tuple[Callable[[str, str], bool], ...] = (
        lambda a, b: a == b,
        lambda a, b: a.rstrip() == b.rstrip(),
        lambda a, b: a.strip() == b.strip(),
        lambda a, b: _normalize_text(a.strip()) == _normalize_text(b.strip()),
    )
    for comparator in comparators:
        for index in offsets:
            if all(
                comparator(source[index + offset], expected[offset])
                for offset in range(width)
            ):
                return index
    return None


def _locate_chunk(
    original: list[str], chunk: _UpdateChunk, line_index: int
) -> tuple[int, list[str], list[str], int] | None:
    """Locate one chunk, returning (start, old, new, next_index)."""
    logger.debug("OpenCode patch chunk location requested", line_index=line_index)
    old, new, anchor = chunk.old, chunk.new, chunk.anchor
    if anchor:
        context_index = _seek_line_match(original, [anchor], line_index)
        if context_index is None:
            return None
        line_index = context_index + 1
    if not old:
        return len(original), [], new, line_index
    pattern = old
    new_slice = new
    start = _seek_line_match(original, pattern, line_index, chunk.eof)
    if start is None and pattern[-1] == "":
        pattern = pattern[:-1]
        if new_slice and new_slice[-1] == "":
            new_slice = new_slice[:-1]
        start = _seek_line_match(original, pattern, line_index, chunk.eof)
    if start is None:
        return None
    return start, pattern, new_slice, start + len(pattern)


def apply_update(source: str, lines: tuple[str, ...]) -> str | None:
    """Apply update hunks using native opencode forward-match semantics."""
    logger.debug("OpenCode forward update requested", line_count=len(lines))
    chunks = _parse_update_chunks(lines)
    if not chunks:
        return None
    bom = source.startswith("\ufeff")
    original = source.removeprefix("\ufeff").split("\n")
    if original[-1] == "":
        original.pop()
    replacements: list[tuple[int, list[str], list[str]]] = []
    line_index = 0
    for chunk in chunks:
        located = _locate_chunk(original, chunk, line_index)
        if located is None:
            return None
        start, old, new, line_index = located
        replacements.append((start, old, new))
    result = list(original)
    replacements.sort(key=lambda item: item[0])
    for start, old, new in reversed(replacements):
        result[start : start + len(old)] = new
    if not result or result[-1] != "":
        result.append("")
    rendered = "\n".join(result)
    return (
        "\ufeff" + rendered if bom and not rendered.startswith("\ufeff") else rendered
    )


def section_content(section: PatchSection, source: str) -> str | None:
    """Render one parsed patch section against its source content."""
    logger.debug("OpenCode patch content requested", operation=section.operation)
    if section.operation == "delete":
        return "" if not section.lines else None
    if section.operation == "update":
        return apply_update(source, section.lines)
    if not all(line.startswith("+") for line in section.lines):
        return None
    content = "\n".join(line[1:] for line in section.lines)
    return content if not content or content.endswith("\n") else content + "\n"


def patch_text(tool_input: ObjectMapping) -> str | None:
    """Return the sole native v2 patch input field."""
    logger.debug("OpenCode patch text requested")
    return string_value(tool_input.get("patchText"))
