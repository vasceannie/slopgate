"""Parse-once infrastructure for lint detectors."""

from __future__ import annotations

import ast
import hashlib
from collections import OrderedDict
from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

from slopgate.lint._helpers.ast_utils import (
    build_parent_map,
    compute_string_line_ranges,
)
from slopgate.lint._helpers.cache_config import (
    REQUEST_ANALYSIS_CACHE_MAX_BYTES,
    REQUEST_ANALYSIS_CACHE_MAX_SOURCE_BYTES,
)
from slopgate.lint._helpers.models import ParsedFile
from slopgate.lint._helpers.paths import relative_path

_TEXT_DECODE_ERROR_POLICY = "replace"


@dataclass(frozen=True, slots=True)
class _ParsedFileCacheEntry:
    signature: tuple[int, int, str]
    size: int
    parsed: ParsedFile


@dataclass(slots=True)
class _RequestAnalysisCacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    bytes_used: int = 0


@dataclass(slots=True)
class _RequestAnalysisCache:
    max_bytes: int = REQUEST_ANALYSIS_CACHE_MAX_BYTES
    max_source_bytes: int = REQUEST_ANALYSIS_CACHE_MAX_SOURCE_BYTES
    entries: OrderedDict[Path, _ParsedFileCacheEntry] = field(
        default_factory=OrderedDict
    )
    stats: _RequestAnalysisCacheStats = field(
        default_factory=_RequestAnalysisCacheStats
    )


_REQUEST_ANALYSIS_CACHE: ContextVar[_RequestAnalysisCache | None] = ContextVar(
    "slopgate_request_analysis_cache", default=None
)


def safe_parse(path: Path) -> ast.Module | None:
    """Parse a Python file, returning None on syntax errors."""
    try:
        source = path.read_text(encoding="utf-8", errors=_TEXT_DECODE_ERROR_POLICY)
        return ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def read_lines(path: Path) -> list[str]:
    """Read a file into a list of lines (empty list on error)."""
    try:
        return path.read_text(
            encoding="utf-8", errors=_TEXT_DECODE_ERROR_POLICY
        ).splitlines()
    except OSError:
        return []


def _request_analysis_cache() -> _RequestAnalysisCache:
    cache = _REQUEST_ANALYSIS_CACHE.get()
    if cache is None:
        cache = _RequestAnalysisCache()
        _REQUEST_ANALYSIS_CACHE.set(cache)
    return cache


def reset_request_analysis_cache() -> None:
    """Clear request-local parsed source/AST analysis."""

    _REQUEST_ANALYSIS_CACHE.set(None)


def request_analysis_cache_stats() -> _RequestAnalysisCacheStats:
    """Return stats for the current request-local analysis cache."""

    cache = _request_analysis_cache()
    return _RequestAnalysisCacheStats(
        hits=cache.stats.hits,
        misses=cache.stats.misses,
        evictions=cache.stats.evictions,
        bytes_used=cache.stats.bytes_used,
    )


def _source_signature(
    stat_size: int, stat_mtime_ns: int, source: str
) -> tuple[int, int, str]:
    digest = hashlib.sha256(
        source.encode("utf-8", errors=_TEXT_DECODE_ERROR_POLICY)
    ).hexdigest()
    return stat_mtime_ns, stat_size, digest


def _cache_entry_size(path: Path, source: str) -> int:
    source_bytes = source.encode("utf-8", errors=_TEXT_DECODE_ERROR_POLICY)
    return len(str(path).encode("utf-8")) + len(source_bytes)


def _remember_parsed_file(
    cache: _RequestAnalysisCache,
    cache_path: Path,
    entry: _ParsedFileCacheEntry,
) -> None:
    if entry.size > cache.max_source_bytes:
        return
    replaced = cache.entries.get(cache_path)
    if replaced is not None:
        cache.stats.bytes_used = max(0, cache.stats.bytes_used - replaced.size)
    cache.entries[cache_path] = entry
    cache.entries.move_to_end(cache_path)
    cache.stats.bytes_used += entry.size
    while cache.stats.bytes_used > cache.max_bytes and cache.entries:
        _, evicted = cache.entries.popitem(last=False)
        cache.stats.bytes_used = max(0, cache.stats.bytes_used - evicted.size)
        cache.stats.evictions += 1


def parse_file(path: Path) -> ParsedFile | None:
    """Parse a Python file into a ``ParsedFile``, or return None on failure."""
    try:
        stat = path.stat()
    except OSError:
        return None
    cache_path = path.resolve()
    cache = _request_analysis_cache()
    try:
        source = path.read_text(encoding="utf-8", errors=_TEXT_DECODE_ERROR_POLICY)
    except (OSError, UnicodeDecodeError):
        return None
    signature = _source_signature(stat.st_size, stat.st_mtime_ns, source)
    cached = cache.entries.get(cache_path)
    if cached is not None and cached.signature == signature:
        cache.stats.hits += 1
        cache.entries.move_to_end(cache_path)
        return cached.parsed

    cache.stats.misses += 1
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return None
    parsed = ParsedFile(
        path=path,
        rel=relative_path(path),
        tree=tree,
        lines=source.splitlines(),
        parent_map=build_parent_map(tree),
        string_line_ranges=compute_string_line_ranges(tree),
    )
    _remember_parsed_file(
        cache,
        cache_path,
        _ParsedFileCacheEntry(
            signature=signature,
            size=_cache_entry_size(cache_path, source),
            parsed=parsed,
        ),
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
