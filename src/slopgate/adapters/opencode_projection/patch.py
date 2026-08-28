"""Parser and pure text application for OpenCode apply_patch input."""

from __future__ import annotations

from collections.abc import Callable

from slopgate._types import ObjectMapping, string_value
from slopgate.util import logger

from .models import PatchOperation, PatchSection, Projection

_HEADERS: tuple[tuple[str, PatchOperation], ...] = (
    ("*** Add File: ", "add"),
    ("*** Update File: ", "update"),
    ("*** Delete File: ", "delete"),
)
_UpdateChunk = tuple[tuple[str, ...], tuple[str, ...], str | None]
_UNICODE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("\u2018", "'"),
    ("\u2019", "'"),
    ("\u201a", "'"),
    ("\u201b", "'"),
    ("\u201c", '"'),
    ("\u201d", '"'),
    ("\u201e", '"'),
    ("\u201f", '"'),
    ("\u2010", "-"),
    ("\u2011", "-"),
    ("\u2012", "-"),
    ("\u2013", "-"),
    ("\u2014", "-"),
    ("\u2015", "-"),
    ("\u2026", "..."),
    ("\u00a0", " "),
)


def _normalize_unicode(line: str) -> str:
    """Normalize Unicode punctuation to ASCII like native opencode."""
    for char, replacement in _UNICODE_REPLACEMENTS:
        line = line.replace(char, replacement)
    return line


def invalid_patch_projection(operation: PatchOperation, relative: str) -> Projection:
    """Return the invalid projection for an unapplicable patch section."""
    logger.debug("OpenCode patch section rejected", operation=operation, path=relative)
    if operation == "update":
        return Projection(
            "invalid", reason="update_hunk_mismatch", target_path=relative
        )
    return Projection("invalid")


def _consume_patch_line(
    line: str,
    active: tuple[PatchOperation, str, str | None] | None,
    body: list[str],
    sections: list[PatchSection],
) -> tuple[tuple[PatchOperation, str, str | None] | None, bool] | None:
    logger.debug("OpenCode patch line consumed", has_active_section=active is not None)
    if line.startswith("*** Move to:"):
        destination = line.removeprefix("*** Move to:").strip()
        if active is None or active[0] != "update" or body:
            return None
        if not destination or active[2] is not None:
            return None
        return (active[0], active[1], destination), False
    header: tuple[PatchOperation, str] | None = None
    for prefix, kind in _HEADERS:
        if line.startswith(prefix):
            header = (kind, line.removeprefix(prefix).strip())
            break
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
    lines = text.splitlines()
    valid_envelope = (
        len(lines) >= 3
        and lines[0] == "*** Begin Patch"
        and lines[-1] == "*** End Patch"
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


def _parse_update_chunks(lines: tuple[str, ...]) -> tuple[_UpdateChunk, ...]:
    logger.debug("OpenCode update chunks parsed", line_count=len(lines))
    chunks: list[_UpdateChunk] = []
    old_lines: list[str] = []
    new_lines: list[str] = []
    anchor: str | None = None
    open_chunk = False
    for line in lines:
        if line.startswith("@@"):
            if open_chunk:
                chunks.append((tuple(old_lines), tuple(new_lines), anchor))
                old_lines, new_lines = [], []
            open_chunk = True
            anchor = line[2:].strip() or None
            continue
        if line == "*** End of File":
            break
        if line.startswith("+"):
            new_lines.append(line[1:])
        elif line.startswith("-"):
            old_lines.append(line[1:])
        elif line.startswith(" "):
            content = line[1:]
            old_lines.append(content)
            new_lines.append(content)
    if open_chunk:
        chunks.append((tuple(old_lines), tuple(new_lines), anchor))
    return tuple(chunks)


def _seek_line_match(
    source: list[str], expected: tuple[str, ...], start: int
) -> int | None:
    """Find the first forward line-block match using native opencode comparators."""
    logger.debug(
        "OpenCode update match requested",
        source_lines=len(source),
        expected_lines=len(expected),
        start_line=start,
    )
    width = len(expected)
    comparators: tuple[Callable[[str, str], bool], ...] = (
        lambda a, b: a == b,
        lambda a, b: a.rstrip() == b.rstrip(),
        lambda a, b: a.strip() == b.strip(),
        lambda a, b: _normalize_unicode(a.strip()) == _normalize_unicode(b.strip()),
    )
    for comparator in comparators:
        for index in range(start, len(source) - width + 1):
            if all(
                comparator(source[index + offset], expected[offset])
                for offset in range(width)
            ):
                return index
    return None


def _locate_chunk(
    original: list[str], chunk: _UpdateChunk, line_index: int
) -> tuple[int, tuple[str, ...], tuple[str, ...], int] | None:
    """Locate one chunk, returning (start, old, new, next_index)."""
    old, new, anchor = chunk
    if anchor is not None:
        context_index = _seek_line_match(original, (anchor,), line_index)
        if context_index is None:
            return None
        line_index = context_index + 1
    if not old:
        insertion_index = (
            len(original) - 1 if original and original[-1] == "" else len(original)
        )
        return insertion_index, (), new, insertion_index
    pattern = old
    new_slice = new
    start = _seek_line_match(original, pattern, line_index)
    if start is None and pattern[-1] == "":
        pattern = pattern[:-1]
        if new_slice and new_slice[-1] == "":
            new_slice = new_slice[:-1]
        start = _seek_line_match(original, pattern, line_index)
    if start is None:
        return None
    return start, pattern, new_slice, start + len(pattern)


def apply_update(source: str, lines: tuple[str, ...]) -> str | None:
    """Apply update hunks using native opencode forward-match semantics."""
    logger.debug("OpenCode forward update requested", line_count=len(lines))
    chunks = _parse_update_chunks(lines)
    if not chunks:
        return None
    trailing_newline = source.endswith("\n")
    original = source.splitlines()
    replacements: list[tuple[int, tuple[str, ...], tuple[str, ...]]] = []
    line_index = 0
    for chunk in chunks:
        located = _locate_chunk(original, chunk, line_index)
        if located is None:
            return None
        start, old, new, line_index = located
        replacements.append((start, old, new))
    result = list(original)
    for start, old, new in reversed(replacements):
        result[start : start + len(old)] = new
    rendered = "\n".join(result)
    return f"{rendered}\n" if trailing_newline else rendered


def section_content(section: PatchSection, source: str) -> str | None:
    """Render one parsed patch section against its source content."""
    logger.debug("OpenCode patch content requested", operation=section.operation)
    if section.operation == "update" and section.move_to and not section.lines:
        return source
    renderers: dict[PatchOperation, Callable[[], str | None]] = {
        "add": lambda: (
            "\n".join(line[1:] for line in section.lines) + "\n"
            if all(line.startswith("+") for line in section.lines)
            else None
        ),
        "update": lambda: apply_update(source, section.lines),
        "delete": lambda: "" if not section.lines else None,
    }
    return renderers[section.operation]()


def patch_text(tool_input: ObjectMapping) -> str | None:
    """Return normalized patch text when aliases do not conflict."""
    camel_present = "patchText" in tool_input
    snake_present = "patch_text" in tool_input
    camel_text = string_value(tool_input.get("patchText"))
    snake_text = string_value(tool_input.get("patch_text"))
    aliases_conflict = camel_present and snake_present and camel_text != snake_text
    logger.debug(
        "OpenCode patch text aliases normalized",
        camel_present=camel_present,
        snake_present=snake_present,
        aliases_conflict=aliases_conflict,
    )
    if aliases_conflict:
        return None
    return camel_text if camel_present else snake_text
