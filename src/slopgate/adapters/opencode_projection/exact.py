"""Native OpenCode v2.2.5 matching and line-ending preservation."""

from __future__ import annotations

import re
from bisect import bisect_left

from slopgate.util import logger

_PUNCTUATION = str.maketrans(
    {
        **dict.fromkeys("‘’‚‛", "'"),
        **dict.fromkeys("“”„‟", '"'),
        **dict.fromkeys("‐‑‒–—―−", "-"),
        **dict.fromkeys(
            "\u00a0\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000",
            " ",
        ),
    }
)


def _normalize_text(value: str) -> str:
    """Apply native one-to-one punctuation and space normalization."""
    logger.debug("OpenCode text normalization requested")
    return value.translate(_PUNCTUATION)


def _occurrences(content: str, search: str) -> list[tuple[int, int]]:
    logger.debug("OpenCode exact matching requested")
    matches: list[tuple[int, int]] = []
    offset = content.find(search)
    while offset >= 0:
        matches.append((offset, offset + len(search)))
        offset = content.find(search, offset + len(search))
    return matches


def _line_occurrences(content: str, search: str) -> list[tuple[int, int]]:
    logger.debug("OpenCode trailing whitespace matching requested")
    trailing = search.endswith("\n")
    expected = search.split("\n")
    if trailing:
        expected.pop()
    lines = [line for line in re.finditer(r"[^\n]*(?:\n|$)", content) if line.group()]
    matches: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        actual = lines[index : index + len(expected)]
        if len(actual) != len(expected):
            continue
        if not all(
            _normalize_text(item.group().rstrip()) == _normalize_text(wanted.rstrip())
            for item, wanted in zip(actual, expected)
        ):
            continue
        last = actual[-1]
        if trailing and not last.group().endswith("\n"):
            continue
        end = last.end() if trailing else last.end() - int(last.group().endswith("\n"))
        if not matches or matches[-1][1] <= line.start():
            matches.append((line.start(), end))
    return matches


def _line_ending(text: str, fallback: str) -> str:
    logger.debug("OpenCode dominant line ending requested")
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    if crlf == lf:
        return fallback
    return "\r\n" if crlf > lf else "\n"


def _align_lines(before: list[str], after: list[str]) -> dict[int, int]:
    logger.debug("OpenCode replacement line alignment requested")
    table = [[0] * (len(after) + 1) for _ in range(len(before) + 1)]
    for i in reversed(range(len(before))):
        for j in reversed(range(len(after))):
            table[i][j] = (
                table[i + 1][j + 1] + 1
                if before[i] == after[j]
                else max(table[i + 1][j], table[i][j + 1])
            )
    aligned: dict[int, int] = {}
    source_gap: list[int] = []
    target_gap: list[int] = []
    i = j = 0
    while i < len(before) and j < len(after):
        if before[i] == after[j]:
            aligned.update(zip(target_gap, source_gap))
            source_gap, target_gap = [], []
            aligned[j] = i
            i, j = i + 1, j + 1
        elif table[i + 1][j] >= table[i][j + 1]:
            source_gap.append(i)
            i += 1
        else:
            target_gap.append(j)
            j += 1
    source_gap.extend(range(i, len(before)))
    target_gap.extend(range(j, len(after)))
    aligned.update(zip(target_gap, source_gap))
    return aligned


def _region_endings(region: str, replacement: str, fallback: str) -> str:
    logger.debug("OpenCode replacement line endings requested")
    before = re.split(r"\r?\n", region)
    endings = re.findall(r"\r?\n", region)
    after = replacement.split("\n")
    aligned = _align_lines(
        [_normalize_text(line.rstrip()) for line in before],
        [_normalize_text(line.rstrip()) for line in after],
    )
    result: list[str] = []
    for index, line in enumerate(after):
        result.append(line)
        if index < len(after) - 1:
            source = aligned.get(index, len(endings))
            result.append(endings[source] if source < len(endings) else fallback)
    return "".join(result)


def _view_matches(view: str, search: str) -> list[tuple[int, int]]:
    logger.debug("OpenCode matching tiers evaluated")
    return (
        _occurrences(view, search)
        or _occurrences(_normalize_text(view), _normalize_text(search))
        or _line_occurrences(view, search)
    )


def _replace_view(source: str, matches: list[tuple[int, int]], new: str) -> str:
    logger.debug("OpenCode matched regions replaced", matches=len(matches))
    removed = [
        match.start() - index for index, match in enumerate(re.finditer("\r\n", source))
    ]
    result = source
    replacement = new.replace("\r\n", "\n")
    fallback = _line_ending(source, "\n")
    for start, end in reversed(matches):
        start += bisect_left(removed, start)
        end += bisect_left(removed, end)
        region = source[start:end]
        content = _region_endings(region, replacement, _line_ending(region, fallback))
        result = result[:start] + content + result[end:]
    return result


def replace_text(source: str, old: str, new: str, replace_all: bool) -> str | None:
    """Return the native unformatted edit, or None for native rejection."""
    logger.debug("OpenCode exact edit projection requested", replace_all=replace_all)
    if not old or old == new:
        return None
    endings_only = old.replace("\r", "") == new.replace("\r", "")
    if endings_only:
        count = source.count(old)
        if not count or (count != 1 and not replace_all):
            return None
        result = source.replace(old, new)
    else:
        matches = _view_matches(source.replace("\r\n", "\n"), old.replace("\r\n", "\n"))
        if not matches or (len(matches) != 1 and not replace_all):
            return None
        result = _replace_view(source, matches, new)
    return result if result != source else None
