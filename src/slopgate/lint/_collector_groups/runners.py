"""Collector runner implementations."""

from __future__ import annotations

from pathlib import Path

from slopgate.lint._collector_groups.enablement import enabled_collectors
from slopgate.lint._collector_groups.source import (
    ast_src_collectors,
    source_analysis,
    structure_src_collectors,
    test_collectors,
)
from slopgate.lint._collector_groups.integrity import (
    full_integrity_collectors,
    touched_integrity_collectors,
)
from slopgate.lint._collector_groups.types import CollectorResults
from slopgate.lint._helpers import parse_files
from slopgate.lint._parse_errors import detect_python_parse_errors
from slopgate.lint.catalog import filter_cataloged_collectors


def run_test_integrity_collectors(
    src_files: list[Path],
    test_files: list[Path],
) -> CollectorResults:
    """Run focused detectors for bad-test-efficacy indicators only."""

    parsed_src = parse_files(src_files)
    parsed_tests = parse_files(test_files)
    results = filter_cataloged_collectors(
        [
            (
                "python-parse-error",
                detect_python_parse_errors([*src_files, *test_files]),
            ),
            *full_integrity_collectors(parsed_src, parsed_tests),
        ],
        "cli",
    )
    return enabled_collectors(results)


def run_touched_collectors(
    src_files: list[Path],
    test_files: list[Path],
    *,
    reference_test_files: list[Path] | None = None,
) -> CollectorResults:
    """Run immediate detectors for touched files."""
    del reference_test_files
    parsed_src, parsed_tests, oversized, literals, _project_index = source_analysis(
        src_files, test_files
    )
    from slopgate.lint._regex_rules import regex_rule_collectors

    results = filter_cataloged_collectors(
        [
            (
                "python-parse-error",
                detect_python_parse_errors([*src_files, *test_files]),
            ),
            *structure_src_collectors(parsed_src, oversized, literals),
            *ast_src_collectors(parsed_src),
            *test_collectors(parsed_tests),
            *regex_rule_collectors(parsed_src, parsed_tests),
            *touched_integrity_collectors(parsed_tests),
        ],
        "hook",
        event="PostToolUse",
    )
    return enabled_collectors(results)


def run_all_collectors(
    src_files: list[Path], test_files: list[Path]
) -> CollectorResults:
    """Run all detectors and return (rule_name, violations) pairs."""
    parsed_src, parsed_tests, oversized, literals, _project_index = source_analysis(
        src_files, test_files
    )
    from slopgate.lint._regex_rules import regex_rule_collectors

    results = filter_cataloged_collectors(
        [
            (
                "python-parse-error",
                detect_python_parse_errors([*src_files, *test_files]),
            ),
            *structure_src_collectors(parsed_src, oversized, literals),
            *ast_src_collectors(parsed_src),
            *test_collectors(parsed_tests),
            *regex_rule_collectors(parsed_src, parsed_tests),
            *full_integrity_collectors(parsed_src, parsed_tests),
        ],
        "cli",
    )
    return enabled_collectors(results)


__all__ = [
    "run_all_collectors",
    "run_test_integrity_collectors",
    "run_touched_collectors",
]
