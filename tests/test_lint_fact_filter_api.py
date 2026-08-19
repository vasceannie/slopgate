"""Contracts for extract-time fact-type filtering."""

from __future__ import annotations

from pathlib import Path

from slopgate.lint._helpers.parsing import parse_file
from slopgate.lint.project_index.extract import extract_file_facts
from slopgate.lint.project_index.fact_filter import fact_type_filter
from slopgate.lint.project_index.facts import FACT_TYPE_LITERALS
from slopgate.lint.project_index.integrity_facts import attach_integrity_facts


def clone_sized_module(root: Path):
    path = root / "mod.py"
    path.write_text(
        "def alpha() -> int:\n"
        "    x = 1\n"
        "    y = 2\n"
        "    z = 3\n"
        "    w = 4\n"
        "    return x + y + z + w\n",
        encoding="utf-8",
    )
    parsed = parse_file(path)
    if parsed is None:
        raise AssertionError("expected parseable module")
    return parsed


def test_fact_type_filter_skips_clone_family(tmp_path: Path) -> None:
    parsed = clone_sized_module(tmp_path)
    with fact_type_filter(frozenset({FACT_TYPE_LITERALS})):
        skipped = extract_file_facts(parsed)
    full = extract_file_facts(parsed)
    assert (skipped.semantic_clones, bool(full.semantic_clones)) == ((), True)


def test_fact_type_filter_skips_integrity_symbols(tmp_path: Path) -> None:
    parsed = clone_sized_module(tmp_path)
    with fact_type_filter(frozenset({FACT_TYPE_LITERALS})):
        attached = attach_integrity_facts(parsed, extract_file_facts(parsed))
    assert attached.production_symbols == ()
