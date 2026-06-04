"""Integration references for lint CLI parser wiring."""

from __future__ import annotations

import argparse

from slopgate.cli.parsers_lint import LintAnalysisParserSpec, add_lint_parsers


def test_lint_parser_spec_fields_are_accessible() -> None:
    spec = LintAnalysisParserSpec(
        name="test-integrity",
        help_text="Run test integrity checks",
        description="Analyze tests",
        details_help="Verbose findings",
        lint_command="test-integrity",
    )
    assert spec.lint_command == "test-integrity"


def test_add_lint_parsers_registers_subcommands() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    add_lint_parsers(sub)
    args = parser.parse_args(["lint", "test-integrity"])
    assert args.lint_command == "test-integrity"
