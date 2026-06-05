"""Tests for repeated-string-literal metadata in duplicate detection."""
# pyright: reportPrivateUsage=false
from __future__ import annotations

from pathlib import Path
from typing import cast

from tests.test_duplicate_detector import _make_parsed
from slopgate.lint._detectors.duplicates import _collect_block_windows
from slopgate.lint._detectors.duplicates import detect_repeated_literals
from slopgate.lint._config import load_config, set_config

class TestRepeatedStringLiteralMetadata:
    def test_records_existing_locations_for_repeated_literals(
        self, tmp_path: Path
    ) -> None:
        _ = (tmp_path / "src").mkdir()
        cfg = load_config(tmp_path)
        set_config(cfg)

        parsed = [
            _make_parsed(
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

        violations = detect_repeated_literals(parsed)
        by_rule = {violation.rule: violation for violation in violations}

        string_locations = cast(
            list[str],
            by_rule["repeated-string-literal"].metadata["existing_locations"],
        )
        magic_locations = cast(
            list[str],
            by_rule["repeated-magic-number"].metadata["existing_locations"],
        )
        assert "src/file_0.py:5" in string_locations
        assert "src/file_10.py:5" in string_locations
        assert "src/file_0.py:7" in magic_locations

    def test_marks_already_defined_constant_match(self, tmp_path: Path) -> None:
        _ = (tmp_path / "src").mkdir()
        _ = (tmp_path / "src" / "constants.py").write_text(
            'SHARED_ERROR = "E_CONN_RESET"\n', encoding="utf-8"
        )
        cfg = load_config(tmp_path)
        set_config(cfg)

        parsed = [
            _make_parsed('print("E_CONN_RESET")\n', rel=f"src/file_{idx}.py")
            for idx in range(11)
        ]
        violations = detect_repeated_literals(parsed)
        repeated = [v for v in violations if v.rule == "repeated-string-literal"]
        assert repeated, "expected repeated-string-literal violation"
        metadata = repeated[0].metadata
        assert "already_defined" in metadata
        already_defined = cast(dict[str, object], metadata["already_defined"])
        assert already_defined["name"] == "SHARED_ERROR"
        assert already_defined["path"] == "src/constants.py"
        assert already_defined["line"] == 1
        assert "src/constants.py:1" in repeated[0].detail
        assert "do not duplicate it or hide the literal with string fragments" in repeated[0].detail

    def test_suggests_candidate_name_when_constant_missing(self, tmp_path: Path) -> None:
        _ = (tmp_path / "src").mkdir()
        cfg = load_config(tmp_path)
        set_config(cfg)

        parsed = [
            _make_parsed('print("retry later")\n', rel=f"src/file_{idx}.py")
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
            _make_parsed(
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
            _make_parsed('event = "PreToolUse"\n', rel=f"src/file_{idx}.py")
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

        groups = _collect_block_windows(
            [_make_parsed(source_a, rel="a.py"), _make_parsed(source_b, rel="b.py")]
        )

        assert groups
        members = [member for group in groups.values() for member in group]
        assert any(rel == "a.py" and start == 4 for rel, _, start, _ in members)
        assert any(rel == "b.py" and start == 4 for rel, _, start, _ in members)
