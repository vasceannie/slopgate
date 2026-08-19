"""Deterministic compact project metadata index for lint analysis."""

from slopgate.lint.project_index.build import build_project_index
from slopgate.lint.project_index.models import (
    ProjectFileSummary,
    ProjectIndex,
    ProjectIndexRequest,
)

__all__ = [
    "ProjectFileSummary",
    "ProjectIndex",
    "ProjectIndexRequest",
    "build_project_index",
]
