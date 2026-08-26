"""Integration references for lint CLI parser wiring."""

from __future__ import annotations

import argparse

from slopgate.cli.parsers.config import add_command_parser, add_config_parsers
from slopgate.cli.parsers.lint import LintAnalysisParserSpec, add_lint_parsers


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


def test_add_command_parser_registers_handler() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    command = add_command_parser(
        sub,
        "sample",
        help_text="Sample command",
        func=str,
    )

    args = parser.parse_args(["sample"])

    assert command.prog.endswith("sample"), "the requested command should be registered"
    assert args.func is str, "the parser should retain the requested handler"


def test_add_config_parsers_registers_path_handler() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    add_config_parsers(sub)

    args = parser.parse_args(["config", "path"])

    assert callable(args.func), "config path should register its command handler"
