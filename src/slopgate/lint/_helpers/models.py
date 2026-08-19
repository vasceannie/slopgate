"""Parsed lint file models."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ParseErrorKind = Literal["syntax", "read"]
PARSE_ERROR_KIND_READ: ParseErrorKind = "read"


@dataclass
class ParsedFile:
    """A Python file pre-parsed for efficient multi-detector scanning.

    Built once per file, shared across all detectors so we never parse
    the same AST or read the same lines twice.
    """

    path: Path
    rel: str
    tree: ast.Module
    lines: list[str]
    parent_map: dict[int, ast.AST] = field(repr=False)
    string_line_ranges: set[int] = field(repr=False)


@dataclass(frozen=True, slots=True)
class FileParseError:
    """Parse or read failure retained from the initial file pass."""

    kind: ParseErrorKind
    message: str
    line: int = 0
    offset: int = 0


@dataclass(frozen=True, slots=True)
class FileSourceSnapshot:
    """Filesystem snapshot used for one parse attempt."""

    path: Path
    size: int
    mtime_ns: int
    source: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class FileParseAttempt:
    """One read/parse of a Python file, including success or failure metadata."""

    path: Path
    size: int
    mtime_ns: int
    source: str
    content_hash: str
    parsed: ParsedFile | None
    error: FileParseError | None

    @classmethod
    def from_snapshot(
        cls,
        snapshot: FileSourceSnapshot,
        *,
        parsed: ParsedFile | None,
        error: FileParseError | None,
    ) -> FileParseAttempt:
        """Build an attempt from a read snapshot and parse outcome."""
        return cls(
            path=snapshot.path,
            size=snapshot.size,
            mtime_ns=snapshot.mtime_ns,
            source=snapshot.source,
            content_hash=snapshot.content_hash,
            parsed=parsed,
            error=error,
        )

    @classmethod
    def read_failure(cls, path: Path, message: str) -> FileParseAttempt:
        """Build an attempt for a file that could not be read."""
        return cls(
            path=path,
            size=0,
            mtime_ns=0,
            source="",
            content_hash="",
            parsed=None,
            error=FileParseError(kind=PARSE_ERROR_KIND_READ, message=message),
        )

    @classmethod
    def syntax_failure(
        cls, snapshot: FileSourceSnapshot, exc: SyntaxError
    ) -> FileParseAttempt:
        """Build an attempt for a file that failed `ast.parse`."""
        return cls.from_snapshot(
            snapshot,
            parsed=None,
            error=FileParseError(
                kind="syntax",
                message=exc.msg,
                line=exc.lineno or 0,
                offset=exc.offset or 0,
            ),
        )

    @classmethod
    def success(
        cls, snapshot: FileSourceSnapshot, parsed: ParsedFile
    ) -> FileParseAttempt:
        """Build an attempt for a file that parsed cleanly."""
        return cls.from_snapshot(snapshot, parsed=parsed, error=None)
