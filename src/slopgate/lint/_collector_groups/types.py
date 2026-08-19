"""Shared collector type aliases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from slopgate.lint._baseline import Violation
from slopgate.lint._helpers import ParsedFile
from slopgate.lint.project_index import ProjectIndex

if TYPE_CHECKING:
    from slopgate.lint._helpers.models import FileParseAttempt
    from slopgate.lint._helpers.profile import LintProfile

SourceAnalysis = tuple[
    list[ParsedFile],
    list[ParsedFile],
    list[Violation],
    list[Violation],
    ProjectIndex,
]
CollectorResults = list[tuple[str, list[Violation]]]


@dataclass(frozen=True, slots=True)
class SourceAnalysisOptions:
    """Optional scan controls for ``source_analysis``."""

    attempts: tuple[FileParseAttempt, ...] | None = None
    active_ids: frozenset[str] | None = None
    build_constants: bool = True
    persist_index: bool = False
    use_index: bool = True
    rebuild_index: bool = False
    profile: LintProfile | None = None
    dirty_paths: tuple[Path, ...] = ()
    parse_paths: tuple[Path, ...] | None = None
    deleted_paths: tuple[Path, ...] = ()
    fact_types: frozenset[str] | None = None


__all__ = ["CollectorResults", "SourceAnalysis", "SourceAnalysisOptions"]
