"""Tests for repeated-string-literal metadata in duplicate detection."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import cast

from slopgate.lint._detectors.duplicates import collect_block_windows
from slopgate.lint._detectors.duplicates import detect_repeated_literals
from slopgate.lint._baseline import Violation
from slopgate.lint._config import load_config, set_config
from slopgate.lint._helpers import (
    ParsedFile,
    build_parent_map,
    compute_string_line_ranges,
)


def make_parsed(source: str, rel: str = "test.py") -> ParsedFile:
    tree = ast.parse(source)
    return ParsedFile(
        path=Path(rel),
        rel=rel,
        tree=tree,
        lines=source.splitlines(),
        parent_map=build_parent_map(tree),
        string_line_ranges=compute_string_line_ranges(tree),
    )


def _repeated_skipped_literal_parsed() -> list[ParsedFile]:
    return [
        make_parsed(
            "from __future__ import annotations\n\n"
            f"LIMIT = {idx}\n"
            "def flag() -> str:\n"
            "    return 'skipped'\n"
            "def window() -> int:\n"
            "    return 24\n",
            rel=f"src/file_{idx}.py",
        )
        for idx in range(11)
    ]


def _violations_by_rule(parsed: list[ParsedFile]) -> dict[str, Violation]:
    return {violation.rule: violation for violation in detect_repeated_literals(parsed)}


class TestRepeatedStringLiteralMetadata:
    def test_records_existing_locations_for_repeated_literals(
        self, tmp_path: Path
    ) -> None:
        _ = (tmp_path / "src").mkdir()
        cfg = load_config(tmp_path)
        set_config(cfg)

        by_rule = _violations_by_rule(_repeated_skipped_literal_parsed())

        string_locations = cast(
            list[str],
            by_rule["repeated-string-literal"].metadata["existing_locations"],
        )
        magic_locations = cast(
            list[str],
            by_rule["repeated-magic-number"].metadata["existing_locations"],
        )
        assert (
            string_locations[0] == "src/file_0.py:5"
            and "src/file_10.py:5" in string_locations
            and magic_locations[0] == "src/file_0.py:7"
        )

    def test_surfaces_existing_locations_in_detail_and_stable_id(
        self, tmp_path: Path
    ) -> None:
        _ = (tmp_path / "src").mkdir()
        set_config(load_config(tmp_path))

        by_rule = _violations_by_rule(_repeated_skipped_literal_parsed())
        cases = (
            (by_rule["repeated-string-literal"], "src/file_0.py:5"),
            (by_rule["repeated-magic-number"], "src/file_0.py:7"),
        )
        assert all(
            f"; locations: {marker}" in violation.detail
            and f"; locations: {marker}" in violation.stable_id
            for violation, marker in cases
        )

    def test_marks_already_defined_constant_match(self, tmp_path: Path) -> None:
        _ = (tmp_path / "src").mkdir()
        _ = (tmp_path / "src" / "constants.py").write_text(
            'SHARED_ERROR = "E_CONN_RESET"\n', encoding="utf-8"
        )
        cfg = load_config(tmp_path)
        set_config(cfg)

        parsed = [
            make_parsed('print("E_CONN_RESET")\n', rel=f"src/file_{idx}.py")
            for idx in range(11)
        ]
        violations = detect_repeated_literals(parsed)
        repeated = [v for v in violations if v.rule == "repeated-string-literal"]
        assert repeated, "expected repeated-string-literal violation"
        metadata = repeated[0].metadata
        assert "already_defined" in metadata, (
            "Expected metadata to identify the existing constant"
        )
        already_defined = cast(dict[str, object], metadata["already_defined"])
        assert already_defined["name"] == "SHARED_ERROR", (
            "Expected existing constant name in metadata"
        )
        assert already_defined["path"] == "src/constants.py", (
            "Expected existing constant path in metadata"
        )
        assert already_defined["line"] == 1, (
            "Expected existing constant line in metadata"
        )
        assert "src/constants.py:1" in repeated[0].detail, (
            "Expected detail to cite existing constant location"
        )
        assert (
            "do not duplicate it or hide the literal with string fragments"
            in repeated[0].detail
        ), "Expected detail to warn against hiding the duplicate literal"

    def test_suggests_candidate_name_when_constant_missing(
        self, tmp_path: Path
    ) -> None:
        _ = (tmp_path / "src").mkdir()
        cfg = load_config(tmp_path)
        set_config(cfg)

        parsed = [
            make_parsed('print("retry later")\n', rel=f"src/file_{idx}.py")
            for idx in range(11)
        ]
        violations = detect_repeated_literals(parsed)
        repeated = [v for v in violations if v.rule == "repeated-string-literal"]
        assert repeated, "expected repeated-string-literal violation"
        metadata = repeated[0].metadata
        assert "candidate_constant_name" in metadata
        assert metadata["candidate_constant_name"] == "RETRY_LATER"

    def test_ignores_repeated_punctuation_delimiters(self, tmp_path: Path) -> None:
        _ = (tmp_path / "src").mkdir()
        cfg = load_config(tmp_path)
        set_config(cfg)

        parsed = [
            make_parsed(
                "\n".join(
                    [
                        'print(":")',
                        'print(".")',
                        'print(")")',
                        'print("`")',
                        'print(", ")',
                    ]
                ),
                rel=f"src/file_{idx}.py",
            )
            for idx in range(11)
        ]
        violations = detect_repeated_literals(parsed)
        repeated = [v for v in violations if v.rule == "repeated-string-literal"]
        assert repeated == []

    def test_keeps_repeated_semantic_event_literal_signal(self, tmp_path: Path) -> None:
        _ = (tmp_path / "src").mkdir()
        cfg = load_config(tmp_path)
        set_config(cfg)

        parsed = [
            make_parsed('event = "PreToolUse"\n', rel=f"src/file_{idx}.py")
            for idx in range(11)
        ]
        violations = detect_repeated_literals(parsed)
        repeated = [v for v in violations if v.rule == "repeated-string-literal"]
        assert len(repeated) == 1
        assert repeated[0].identifier == "'PreToolUse'"
        assert repeated[0].metadata["candidate_constant_name"] == "PRE_TOOL_USE"

    def test_same_body_different_imports_duplicate_alert_still_fires(self):
        """Body-only duplicate detection still works when imports differ."""
        source_a = (
            "import os\n"
            "import json\n"
            "import sys\n"
            "x = normalize(data)\n"
            "y = x + 1\n"
            "return y\n"
        )
        source_b = (
            "import requests\n"
            "from pathlib import Path\n"
            "from slopgate.engine import evaluate_payload\n"
            "x = normalize(payload)\n"
            "y = x + 1\n"
            "return y\n"
        )

        groups = collect_block_windows(
            [make_parsed(source_a, rel="a.py"), make_parsed(source_b, rel="b.py")]
        )

        assert groups
        members = [member for group in groups.values() for member in group]
        assert any(rel == "a.py" and start == 4 for rel, _, start, _ in members)
        assert any(rel == "b.py" and start == 4 for rel, _, start, _ in members)
