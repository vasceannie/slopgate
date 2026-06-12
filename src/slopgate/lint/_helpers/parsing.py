"""Parse-once infrastructure for lint detectors."""

from __future__ import annotations

import ast
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from slopgate.lint._helpers.ast_utils import (
    build_parent_map,
    compute_string_line_ranges,
)
from slopgate.lint._helpers.models import ParsedFile
from slopgate.lint._helpers.paths import relative_path


@dataclass(frozen=True, slots=True)
class _ParsedFileCacheEntry:
    mtime_ns: int
    size: int
    parsed: ParsedFile


_PARSED_FILE_CACHE: dict[Path, _ParsedFileCacheEntry] = {}
_PARSED_FILE_CACHE_LOCK = threading.Lock()


def safe_parse(path: Path) -> ast.Module | None:
    """Parse a Python file, returning None on syntax errors."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        return ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def read_lines(path: Path) -> list[str]:
    """Read a file into a list of lines (empty list on error)."""
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def parse_file(path: Path) -> ParsedFile | None:
    """Parse a Python file into a ``ParsedFile``, or return None on failure."""
    try:
        stat = path.stat()
    except OSError:
        return None
    cache_path = path.resolve()
    with _PARSED_FILE_CACHE_LOCK:
        cached = _PARSED_FILE_CACHE.get(cache_path)
    if (
        cached is not None
        and cached.mtime_ns == stat.st_mtime_ns
        and cached.size == stat.st_size
    ):
        return cached.parsed

    tree = safe_parse(path)
    if tree is None:
        return None
    parsed = ParsedFile(
        path=path,
        rel=relative_path(path),
        tree=tree,
        lines=read_lines(path),
        parent_map=build_parent_map(tree),
        string_line_ranges=compute_string_line_ranges(tree),
    )
    with _PARSED_FILE_CACHE_LOCK:
        _PARSED_FILE_CACHE[cache_path] = _ParsedFileCacheEntry(
            mtime_ns=stat.st_mtime_ns,
            size=stat.st_size,
            parsed=parsed,
        )
    return parsed


def parse_files(paths: list[Path]) -> list[ParsedFile]:
    """Parse a list of Python files, skipping any that fail to parse."""
    results: list[ParsedFile] = []
    for path in paths:
        parsed = parse_file(path)
        if parsed is not None:
            results.append(parsed)
    return results


def ensure_parsed(
    files: Sequence[Path | ParsedFile] | None,
    fallback: list[Path] | None = None,
) -> list[ParsedFile]:
    """Accept raw ``Path`` list, ``ParsedFile`` list, or ``None``."""
    if files is None:
        if fallback is not None:
            return parse_files(fallback)
        return []
    if not files:
        return []
    first = files[0]
    if isinstance(first, ParsedFile):
        return [item for item in files if isinstance(item, ParsedFile)]
    return parse_files([item for item in files if isinstance(item, Path)])
