"""Tests for repeated-block import canonicalization behavior."""
# pyright: reportPrivateUsage=false
from __future__ import annotations

import ast
from pathlib import Path
from typing import cast

from slopgate.lint._detectors.duplicates import _collect_block_windows
from slopgate.lint._detectors.duplicates import detect_repeated_blocks
from slopgate.lint._detectors.duplicates import detect_repeated_literals
from slopgate.lint._config import load_config, set_config
from slopgate.lint._helpers import (
    ParsedFile,
    build_parent_map,
    compute_string_line_ranges,
)


def _make_parsed(source: str, rel: str = "test.py") -> ParsedFile:
    tree = ast.parse(source)
    return ParsedFile(
        path=Path(rel),
        rel=rel,
        tree=tree,
        lines=source.splitlines(),
        parent_map=build_parent_map(tree),
        string_line_ranges=compute_string_line_ranges(tree),
    )


class TestCollectBlockWindowsImportExclusion:
    def test_pure_import_window_not_hashed(self):
        """A module-level body of 3 import statements produces no block windows."""
        source = "import os\nimport sys\nimport json\n"
        groups = _collect_block_windows([_make_parsed(source)])
        assert len(groups) == 0

    def test_same_import_block_in_two_files_no_violation(self):
        """Identical 3-import headers across files produce no repeated-code-block."""
        source = "import os\nimport sys\nimport json\n"
        pf1 = _make_parsed(source, rel="a.py")
        pf2 = _make_parsed(source, rel="b.py")
        groups = _collect_block_windows([pf1, pf2])
        assert len(groups) == 0

    def test_windows_overlapping_leading_import_block_are_excluded(self):
        """Boundary windows that include the leading import block are excluded."""
        source = "import os\nimport sys\nx = 1\n"
        groups = _collect_block_windows([_make_parsed(source)])
        assert len(groups) == 0

    def test_from_import_window_excluded(self):
        """from-import statements are also excluded when all-import."""
        source = (
            "from os import path\n"
            "from sys import argv\n"
            "from json import dumps\n"
        )
        groups = _collect_block_windows([_make_parsed(source)])
        assert len(groups) == 0

    def test_all_import_body_in_function_excluded(self):
        """Import statements inside a function body are also excluded."""
        source = (
            "def setup():\n"
            "    import os\n"
            "    import sys\n"
            "    import json\n"
        )
        groups = _collect_block_windows([_make_parsed(source)])
        assert len(groups) == 0


class TestCollectBlockWindowsDeclarativeConstants:
    def test_module_constant_window_not_hashed(self) -> None:
        """Uppercase module constants are declarative data, not copied behavior."""
        source = (
            '_DOCUMENT_DETAIL_KEYS = ("resume_file", "cover_letter_file")\n'
            '_TAILORING_DECISION_KEY = "tailoring_decision"\n'
            '_TAILORING_SIGNALS_KEY = "tailoring_signals"\n'
        )

        groups = _collect_block_windows([_make_parsed(source)])

        assert groups == {}

    def test_same_module_constant_shape_in_two_files_no_violation(self) -> None:
        """Readable separate constants should not need tuple-assignment workarounds."""
        submit_preview = (
            '_DOCUMENT_DETAIL_KEYS = ("resume_file", "cover_letter_file")\n'
            '_TAILORING_DECISION_KEY = "tailoring_decision"\n'
            '_TAILORING_SIGNALS_KEY = "tailoring_signals"\n'
        )
        document_preview = (
            '_COVER_TERMS = ("cover", "letter")\n'
            '_DOCUMENT_LOADING_BODY = "Loading…"\n'
            '_DOCUMENT_BODY_ID = "document-preview-body"\n'
        )

        violations = detect_repeated_blocks(
            [
                _make_parsed(submit_preview, rel="submit_preview.py"),
                _make_parsed(document_preview, rel="document_preview.py"),
            ]
        )

        assert [v for v in violations if v.rule == "repeated-code-block"] == []

    def test_logger_plus_module_constants_shape_no_violation(self) -> None:
        """Standard logger + constants scaffolds are declarations, not behavior."""
        extraction = (
            "logger = get_logger(__name__)\n"
            '_FRAME_DEPTH_FMT = "Switched to frame {} (depth {})"\n'
            '_FIELD_DISCOVERED_FMT = "Field discovered: {} ({})"\n'
        )
        tailor_node = (
            "logger = get_logger(__name__)\n"
            '_TAILOR_PHASE = "tailor_documents"\n'
            '_TAILORING_FAILURE_WARNING = "Resume tailoring failed"\n'
        )

        violations = detect_repeated_blocks(
            [_make_parsed(extraction, rel="extraction.py"), _make_parsed(tailor_node, rel="_node.py")]
        )

        assert [v for v in violations if v.rule == "repeated-code-block"] == []

    def test_logger_constant_reorder_shape_no_violation(self) -> None:
        """Hash-breaking declaration order should not be necessary either."""
        extraction = (
            '_FRAME_DEPTH_FMT = "Switched to frame {} (depth {})"\n'
            "logger = get_logger(__name__)\n"
            '_FIELD_DISCOVERED_FMT = "Field discovered: {} ({})"\n'
        )
        tailor_node = (
            "logger = get_logger(__name__)\n"
            '_TAILOR_PHASE = "tailor_documents"\n'
            '_TAILORING_FAILURE_WARNING = "Resume tailoring failed"\n'
        )

        violations = detect_repeated_blocks(
            [_make_parsed(extraction, rel="extraction.py"), _make_parsed(tailor_node, rel="_node.py")]
        )

        assert [v for v in violations if v.rule == "repeated-code-block"] == []

    def test_side_effectful_module_duplicate_still_fires(self) -> None:
        """Only declarative constants are skipped; module behavior remains guarded."""
        source_a = (
            'register("resume")\n'
            "configure(client)\n"
            "connect(client)\n"
        )
        source_b = (
            'register("cover")\n'
            "configure(adapter)\n"
            "connect(adapter)\n"
        )

        violations = detect_repeated_blocks(
            [_make_parsed(source_a, rel="a.py"), _make_parsed(source_b, rel="b.py")]
        )

        assert len([v for v in violations if v.rule == "repeated-code-block"]) == 2

    def test_safe_constant_factory_window_not_hashed(self) -> None:
        """Established constant factory calls should not require hash camouflage."""
        source_a = (
            '_CHOICE_WIDGETS = frozenset({"checkbox", "radio", "select"})\n'
            '_SAMPLE_BOOLEAN_VALUE = "".join(("tr", "ue"))\n'
            '_STATUS_OK = cast(Status, "ok")\n'
        )
        source_b = (
            '_TEXT_SUFFIXES = frozenset({".md", ".txt"})\n'
            '_UNKNOWN_SUFFIX = "".join(("un", "known"))\n'
            '_STATUS_WARNING = cast(Status, "warning")\n'
        )

        violations = detect_repeated_blocks(
            [_make_parsed(source_a, rel="a.py"), _make_parsed(source_b, rel="b.py")]
        )

        assert [v for v in violations if v.rule == "repeated-code-block"] == []


class TestCollectBlockWindowsImportCanonicalization:
    def test_same_imports_different_order_no_duplicate_alert(self):
        """Same leading imports in different order do not affect body scoring."""
        source_a = (
            "import os\n"
            "import json\n"
            "import sys\n"
            "x = normalize(data)\n"
            "y = x + 1\n"
            "return y\n"
        )
        source_b = (
            "import sys\n"
            "import os\n"
            "import json\n"
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


