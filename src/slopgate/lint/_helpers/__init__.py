"""Shared helpers for quality-gate detectors and tests."""

from __future__ import annotations

from .ast_utils import (
    build_parent_map,
    class_body_lines,
    compute_string_line_ranges,
    count_methods,
    enclosing_function,
    function_body_lines,
    without_leading_docstring,
)
from .discovery import find_all_python_files, find_source_files, find_test_files
from .models import ParsedFile
from .parsing import ensure_parsed, parse_file, parse_files, read_lines, safe_parse
from .paths import (
    project_root,
    relative_path,
    src_root,
    src_roots,
    test_roots,
    tests_root,
)

__all__ = [
    "ParsedFile",
    "build_parent_map",
    "class_body_lines",
    "compute_string_line_ranges",
    "count_methods",
    "enclosing_function",
    "ensure_parsed",
    "find_all_python_files",
    "find_source_files",
    "find_test_files",
    "function_body_lines",
    "parse_file",
    "parse_files",
    "project_root",
    "read_lines",
    "relative_path",
    "safe_parse",
    "src_root",
    "src_roots",
    "test_roots",
    "tests_root",
    "without_leading_docstring",
]
