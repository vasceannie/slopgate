from __future__ import annotations

import ast
from pathlib import Path

from hypothesis import given, strategies

import slopgate.lint._collectors
from slopgate.lint._helpers import (
    ParsedFile,
    build_parent_map,
    compute_string_line_ranges,
)

STRUCTURE_RULE_NAMES = {
    "feature-envy",
    "import-fanout",
    "import-alias",
    "private-import-chain",
    "dead-code",
    "flat-sibling-files",
    "high-complexity",
    "long-method",
    "too-many-params",
    "deep-nesting",
    "god-class",
    "oversized-module",
    "oversized-module-soft",
    "semantic-clone",
    "repeated-magic-number",
    "repeated-string-literal",
    "repeated-code-block",
    "duplicate-call-sequence",
}
SOURCE_PATH = "src/pkg/core.py"
TEST_PATH = "tests/test_core.py"
SOURCE_BODY = "def parse_payload(value):\n    return value\n"
TEST_BODY = "def test_parse_payload():\n    assert True\n"


def _parsed(source: str, rel: str) -> ParsedFile:
    tree = ast.parse(source)
    return ParsedFile(
        path=Path("/tmp/project") / rel,
        rel=rel,
        tree=tree,
        lines=source.splitlines(),
        parent_map=build_parent_map(tree),
        string_line_ranges=compute_string_line_ranges(tree),
    )


def _collector_groups_for_fixture() -> tuple[set[str], set[str]]:
    parsed_src = [_parsed(SOURCE_BODY, SOURCE_PATH)]
    parsed_tests = [_parsed(TEST_BODY, TEST_PATH)]

    source_names = {
        name
        for name, _violations in slopgate.lint._collectors.structure_src_collectors(
            parsed_src, [], []
        )
    } | {
        name
        for name, _violations in slopgate.lint._collectors.ast_src_collectors(
            parsed_src
        )
    }
    test_names = {
        name
        for name, _violations in slopgate.lint._collectors.test_collectors(parsed_tests)
    }
    return source_names, test_names


@given(strategies.just(None))
def test_structure_src_collectors_preserve_rule_catalog_shape(
    _sentinel: None,
) -> None:
    collector_names = {
        name
        for name, _violations in slopgate.lint._collectors.structure_src_collectors(
            [], [], []
        )
    }

    assert collector_names == STRUCTURE_RULE_NAMES, (
        "Structure source collectors should expose a stable rule catalog shape"
    )


def test_source_collectors_keep_duplicate_and_literal_checks_immediate() -> None:
    source_group_names, _test_group_names = _collector_groups_for_fixture()

    assert {"duplicate-call-sequence", "repeated-string-literal"}.issubset(
        source_group_names
    ), "Touched source collectors should keep duplicate and literal checks immediate"


def test_base_test_collectors_stay_separate_from_touched_integrity() -> None:
    _source_group_names, test_group_names = _collector_groups_for_fixture()

    assert "weak-test-assertion" not in test_group_names, (
        "Base test collectors should stay separate from touched integrity collectors"
    )
