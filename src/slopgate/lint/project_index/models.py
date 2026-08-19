"""Project index request and summary models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from slopgate.constants import PROJECT_INDEX_CACHE_MAX_BYTES
from slopgate.lint.project_index.facts import FileAnalysisFacts

if TYPE_CHECKING:
    from slopgate.lint._helpers.models import FileParseAttempt


@dataclass(frozen=True, slots=True)
class ProjectIndexRequest:
    """Inputs for one deterministic project index build."""

    root: Path
    src_files: tuple[Path, ...]
    test_files: tuple[Path, ...]
    dirty_paths: tuple[Path, ...] = ()
    attempts: tuple[FileParseAttempt, ...] | None = None
    persist: bool = False
    use_store: bool = True
    rebuild: bool = False
    max_bytes: int = PROJECT_INDEX_CACHE_MAX_BYTES
    fact_types: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class ProjectFileSummary:
    """Compact metadata for one indexed project file."""

    path: Path
    relative_path: str
    kind: str
    size: int
    mtime_ns: int
    content_hash: str
    symbols: tuple[str, ...]
    imports: tuple[str, ...]
    duplicate_fingerprint: str
    facts: FileAnalysisFacts = field(default_factory=FileAnalysisFacts)


@dataclass(frozen=True, slots=True)
class ProjectIndex:
    """Deterministic project file inventory for hook and CLI lint surfaces."""

    root: Path
    files: tuple[ProjectFileSummary, ...]
    dirty_paths: tuple[str, ...]
    bytes_used: int
    max_bytes: int
    by_relative_path: dict[str, ProjectFileSummary] = field(repr=False)

    @classmethod
    def from_summaries(
        cls,
        root: Path,
        request: ProjectIndexRequest,
        summaries: tuple[ProjectFileSummary, ...],
        bytes_used: int,
    ) -> ProjectIndex:
        """Assemble an index and relative-path lookup from compact summaries."""
        dirty_paths = tuple(
            sorted(
                {
                    path.resolve().relative_to(root).as_posix()
                    for path in request.dirty_paths
                    if path.resolve().is_relative_to(root)
                }
            )
        )
        return cls(
            root=root,
            files=summaries,
            dirty_paths=dirty_paths,
            bytes_used=bytes_used,
            max_bytes=request.max_bytes,
            by_relative_path={
                summary.relative_path: summary for summary in summaries
            },
        )
