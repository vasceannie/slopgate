"""Shared collector type aliases."""

from __future__ import annotations

from slopgate.lint._baseline import Violation
from slopgate.lint._helpers import ParsedFile
from slopgate.lint.project_index import ProjectIndex

SourceAnalysis = tuple[
    list[ParsedFile],
    list[ParsedFile],
    list[Violation],
    list[Violation],
    ProjectIndex,
]
CollectorResults = list[tuple[str, list[Violation]]]

__all__ = ["CollectorResults", "SourceAnalysis"]
