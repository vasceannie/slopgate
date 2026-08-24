"""Parser and pure text application for OpenCode apply_patch input."""

from __future__ import annotations

from collections.abc import Callable

from slopgate._types import ObjectMapping, string_value
from slopgate.util import logger

from .models import PatchOperation, PatchSection

_HEADERS: tuple[tuple[str, PatchOperation], ...] = (
    ("*** Add File: ", "add"),
    ("*** Update File: ", "update"),
    ("*** Delete File: ", "delete"),
)
_UpdateChunk = tuple[tuple[str, ...], tuple[str, ...]]


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
    active: tuple[PatchOperation, str] | None = None
    body: list[str] = []
    for line in lines[1:-1]:
        header: tuple[PatchOperation, str] | None = None
        for prefix, kind in _HEADERS:
            if line.startswith(prefix):
                header = (kind, line.removeprefix(prefix).strip())
                break
        if header is None:
            if active is None:
                return None
            body.append(line)
            continue
        if active is not None:
            sections.append(PatchSection(*active, tuple(body)))
        active = header
        body = []
    if active is None:
        return None
    sections.append(PatchSection(*active, tuple(body)))
    return tuple(sections)


def _parse_update_chunks(lines: tuple[str, ...]) -> tuple[_UpdateChunk, ...]:
    logger.debug("OpenCode update chunks parsed", line_count=len(lines))
    chunks: list[_UpdateChunk] = []
    old_lines: list[str] = []
    new_lines: list[str] = []
    for line in lines:
        if line.startswith("@@"):
            if old_lines:
                chunks.append((tuple(old_lines), tuple(new_lines)))
                old_lines, new_lines = [], []
            continue
        if line.startswith("+"):
            new_lines.append(line[1:])
        elif line.startswith("-"):
            old_lines.append(line[1:])
        else:
            context = line[1:] if line.startswith(" ") else line
            old_lines.append(context)
            new_lines.append(context)
    if old_lines:
        chunks.append((tuple(old_lines), tuple(new_lines)))
    return tuple(chunks)


def _unique_line_match(source: list[str], expected: tuple[str, ...]) -> int | None:
    logger.debug(
        "OpenCode update match requested",
        source_lines=len(source),
        expected_lines=len(expected),
    )
    width = len(expected)
    matches = [
        index
        for index in range(len(source) - width + 1)
        if tuple(source[index : index + width]) == expected
    ]
    return matches[0] if len(matches) == 1 else None


def apply_update(source: str, lines: tuple[str, ...]) -> str | None:
    """Apply exact, uniquely matching update hunks to in-memory content."""
    logger.debug("OpenCode exact update requested", line_count=len(lines))
    chunks = _parse_update_chunks(lines)
    if not chunks:
        return None
    trailing_newline = source.endswith("\n")
    result = source.splitlines()
    for old, new in chunks:
        start = _unique_line_match(result, old)
        if start is None:
            return None
        width = len(old)
        result[start : start + width] = new
    rendered = "\n".join(result)
    return f"{rendered}\n" if trailing_newline else rendered


def section_content(section: PatchSection, source: str) -> str | None:
    """Render one parsed patch section against its source content."""
    logger.debug("OpenCode patch content requested", operation=section.operation)
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
