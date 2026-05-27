from __future__ import annotations

import ast
from pathlib import Path

from vibeforcer.lint._detectors.line_length import detect_long_lines
from vibeforcer.lint._helpers import (
    ParsedFile,
    build_parent_map,
    compute_string_line_ranges,
)


def _make_parsed(source: str, rel: str = "src/example.py") -> ParsedFile:
    tree = ast.parse(source)
    return ParsedFile(
        path=Path(rel),
        rel=rel,
        tree=tree,
        lines=source.splitlines(),
        parent_map=build_parent_map(tree),
        string_line_ranges=compute_string_line_ranges(tree),
    )


def test_long_line_detector_ignores_docstring_lines() -> None:
    source = '"""' + ("doc " * 40) + '"""\n'
    assert detect_long_lines([_make_parsed(source)]) == []


def test_long_line_detector_ignores_whitespace_only_lines() -> None:
    source = "def ok():\n" + (" " * 180) + "\n    return 1\n"
    assert detect_long_lines([_make_parsed(source)]) == []


def test_long_line_detector_ignores_trailing_spaces() -> None:
    source = "value = 1" + (" " * 180) + "\n"
    assert detect_long_lines([_make_parsed(source)]) == []


def test_long_line_detector_still_flags_executable_long_line() -> None:
    source = "value = " + " + ".join(["name"] * 30) + "\n"
    violations = detect_long_lines([_make_parsed(source)])
    assert [violation.rule for violation in violations] == ["long-line"]
