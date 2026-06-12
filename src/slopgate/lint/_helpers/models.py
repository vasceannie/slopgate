"""Parsed lint file models."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


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
