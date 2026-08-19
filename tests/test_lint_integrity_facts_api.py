"""Contracts for persisted integrity facts and extract helpers."""

from __future__ import annotations

from pathlib import Path

from slopgate.lint._helpers.models import ParsedFile
from slopgate.lint._helpers.parsing import parse_file
from slopgate.lint.project_index.extract import extract_file_facts
from slopgate.lint.project_index.integrity_facts import (
    attach_integrity_facts,
    integrity_index_from_project,
    stale_reference_violations,
)
from slopgate.lint.project_index.models import ProjectIndex, ProjectIndexRequest


def parsed_module(root: Path) -> ParsedFile:
    path = root / "mod.py"
    path.write_text("def alpha() -> int:\n    return 1\n", encoding="utf-8")
    parsed = parse_file(path)
    if parsed is None:
        raise AssertionError("expected parseable module")
    return parsed


def empty_index(root: Path) -> ProjectIndex:
    if not root.is_absolute():
        raise ValueError("root must be absolute")
    return ProjectIndex.from_summaries(
        root,
        ProjectIndexRequest(root=root, src_files=(), test_files=()),
        (),
        0,
    )


def test_extract_file_facts_counts_lines(tmp_path: Path) -> None:
    assert extract_file_facts(parsed_module(tmp_path)).line_count == 2


def test_attach_integrity_facts_records_symbol(tmp_path: Path) -> None:
    parsed = parsed_module(tmp_path)
    attached = attach_integrity_facts(parsed, extract_file_facts(parsed))
    assert attached.production_symbols[0].name == "alpha"


def test_integrity_index_from_empty_project(tmp_path: Path) -> None:
    assert integrity_index_from_project(empty_index(tmp_path)).production_call_sites == {}


def test_stale_reference_violations_empty(tmp_path: Path) -> None:
    assert stale_reference_violations(empty_index(tmp_path)) == []
