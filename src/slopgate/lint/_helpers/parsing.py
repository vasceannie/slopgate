"""Parse-once infrastructure for lint detectors."""

from __future__ import annotations

import ast
import hashlib
import os
from collections import OrderedDict
from collections.abc import Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

from typing_extensions import TypeIs

from slopgate.constants import LINT_CACHE_COUNTER_STEP
from slopgate.lint._helpers.ast_utils import (
    build_parent_map,
    compute_string_line_ranges,
)
from slopgate.lint._helpers.cache_config import (
    REQUEST_ANALYSIS_CACHE_MAX_BYTES,
    REQUEST_ANALYSIS_CACHE_MAX_SOURCE_BYTES,
)
from slopgate.lint._helpers.models import (
    FileParseAttempt,
    FileSourceSnapshot,
    ParsedFile,
)
from slopgate.lint._helpers.paths import relative_path

_TEXT_DECODE_ERROR_POLICY = "replace"

_PathFallback: TypeAlias = list[Path] | Callable[[], list[Path]]


def _is_eager_fallback(fallback: _PathFallback) -> TypeIs[list[Path]]:
    """Narrow the legacy eager fallback form for strict type checking."""
    return isinstance(fallback, list)


@dataclass(frozen=True, slots=True)
class _ParsedFileCacheEntry:
    signature: tuple[int, int, str]
    size: int
    attempt: FileParseAttempt


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
_REQUEST_COLLECTOR_MS: ContextVar[int] = ContextVar(
    "slopgate_request_collector_ms", default=0
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


def record_request_collector_ms(elapsed_ms: int) -> None:
    """Accumulate collector latency for the active evaluation request."""
    _REQUEST_COLLECTOR_MS.set(_REQUEST_COLLECTOR_MS.get() + elapsed_ms)


def reset_request_timing() -> int:
    """Return and clear request-local collector latency."""
    elapsed_ms = _REQUEST_COLLECTOR_MS.get()
    _REQUEST_COLLECTOR_MS.set(0)
    return elapsed_ms


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
        cache.stats.evictions += LINT_CACHE_COUNTER_STEP


def _lookup_cached_by_stat(
    cache: _RequestAnalysisCache,
    cache_path: Path,
    stat: os.stat_result,
) -> FileParseAttempt | None:
    cached = cache.entries.get(cache_path)
    if cached is None:
        return None
    mtime_ns, size, _digest = cached.signature
    if mtime_ns != stat.st_mtime_ns or size != stat.st_size:
        return None
    cache.stats.hits += LINT_CACHE_COUNTER_STEP
    cache.entries.move_to_end(cache_path)
    return cached.attempt


def _attempt_from_snapshot(snapshot: FileSourceSnapshot) -> FileParseAttempt:
    try:
        tree = ast.parse(snapshot.source, filename=str(snapshot.path))
    except SyntaxError as exc:
        return FileParseAttempt.syntax_failure(snapshot, exc)
    parsed = ParsedFile(
        path=snapshot.path,
        rel=relative_path(snapshot.path),
        tree=tree,
        lines=snapshot.source.splitlines(),
        parent_map=build_parent_map(tree),
        string_line_ranges=compute_string_line_ranges(tree),
    )
    return FileParseAttempt.success(snapshot, parsed)


def _read_source_snapshot(
    path: Path, stat: os.stat_result | None = None
) -> FileSourceSnapshot | FileParseAttempt:
    try:
        file_stat = path.stat() if stat is None else stat
        source = path.read_text(encoding="utf-8", errors=_TEXT_DECODE_ERROR_POLICY)
    except (OSError, UnicodeDecodeError) as exc:
        return FileParseAttempt.read_failure(path, type(exc).__name__)
    signature = _source_signature(file_stat.st_size, file_stat.st_mtime_ns, source)
    return FileSourceSnapshot(
        path=path,
        size=file_stat.st_size,
        mtime_ns=file_stat.st_mtime_ns,
        source=source,
        content_hash=signature[2],
    )


def parse_file_attempt(path: Path) -> FileParseAttempt:
    """Read and parse a Python file once, retaining success or error metadata."""
    cache = _request_analysis_cache()
    cache_path = path.resolve()
    try:
        stat = path.stat()
    except OSError as exc:
        return FileParseAttempt.read_failure(path, type(exc).__name__)
    cached = _lookup_cached_by_stat(cache, cache_path, stat)
    if cached is not None:
        return cached
    snapshot = _read_source_snapshot(path, stat)
    if isinstance(snapshot, FileParseAttempt):
        return snapshot
    signature = (snapshot.mtime_ns, snapshot.size, snapshot.content_hash)
    cache.stats.misses += LINT_CACHE_COUNTER_STEP
    attempt = _attempt_from_snapshot(snapshot)
    _remember_parsed_file(
        cache,
        cache_path,
        _ParsedFileCacheEntry(
            signature=signature,
            size=_cache_entry_size(cache_path, snapshot.source),
            attempt=attempt,
        ),
    )
    return attempt


def parse_file_attempts(paths: Sequence[Path]) -> list[FileParseAttempt]:
    """Parse each path once and retain success or error metadata."""
    from slopgate.lint._helpers.parallel import (
        parse_attempts_parallel,
        should_parse_in_parallel,
    )

    unique_paths = list(paths)
    if should_parse_in_parallel(unique_paths):
        return parse_attempts_parallel(unique_paths)
    return [parse_file_attempt(path) for path in unique_paths]


def parse_file(path: Path) -> ParsedFile | None:
    """Parse a Python file into a ``ParsedFile``, or return None on failure."""
    return parse_file_attempt(path).parsed


def parse_files(paths: list[Path]) -> list[ParsedFile]:
    """Parse a list of Python files, skipping any that fail to parse."""
    return [
        attempt.parsed
        for attempt in parse_file_attempts(paths)
        if attempt.parsed is not None
    ]


def ensure_parsed(
    files: Sequence[Path | ParsedFile] | None,
    fallback: _PathFallback | None = None,
) -> list[ParsedFile]:
    """Accept raw ``Path`` list, ``ParsedFile`` list, or ``None``."""
    if files is None:
        if fallback is not None:
            if _is_eager_fallback(fallback):
                return parse_files(fallback)
            return parse_files(fallback())
        return []
    if not files:
        return []
    first = files[0]
    if isinstance(first, ParsedFile):
        return [item for item in files if isinstance(item, ParsedFile)]
    return parse_files([item for item in files if isinstance(item, Path)])
