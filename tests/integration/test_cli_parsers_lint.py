"""Integration references for lint CLI parser wiring."""

from __future__ import annotations

import argparse

from slopgate.cli._migrate import cmd_migrate
from slopgate.cli.commands import cmd_eval, cmd_stats
from slopgate.cli.parsers.config import (
    add_command_parser,
    add_config_parsers,
    add_path_command_parser,
)
from slopgate.cli.parsers.lint import LintAnalysisParserSpec, add_lint_parsers
from slopgate.cli.parsers.maintenance import add_eval_parser, add_maintenance_parsers


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


def test_add_path_command_parser_defaults_to_the_current_directory() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    add_path_command_parser(sub, "sample", help_text="Sample command", func=str)

    args = parser.parse_args(["sample"])

    assert (args.path, args.func) == (".", str), (
        "path commands should default to '.' and keep their handler"
    )


def test_add_eval_parser_routes_pack_options_to_cmd_eval() -> None:
    parser = argparse.ArgumentParser()
    add_eval_parser(parser.add_subparsers(dest="command"))

    args = parser.parse_args(
        ["eval", "--pack", "cases.jsonl", "--limit", "3", "--pretty", "--include-label-only"]
    )

    parsed = (args.pack, args.limit, args.pretty, args.verbose, args.include_label_only)
    assert parsed == ("cases.jsonl", 3, True, False, True), (
        "eval flags should parse independently of each other"
    )
    assert args.func is cmd_eval, "eval should dispatch to cmd_eval"


def test_add_maintenance_parsers_registers_stats_and_migrate() -> None:
    parser = argparse.ArgumentParser()
    add_maintenance_parsers(parser.add_subparsers(dest="command"))

    stats = parser.parse_args(["stats", "--baseline-policy", "abc", "--cohort", "a=b"])
    migrate = parser.parse_args(["migrate", "repo", "--user-only"])

    assert (stats.func, stats.baseline_policy, stats.cohort) == (cmd_stats, "abc", ["a=b"]), (
        "stats should keep its fingerprint and cohort options"
    )
    assert (migrate.func, migrate.path, migrate.user_only, migrate.force) == (
        cmd_migrate,
        "repo",
        True,
        False,
    ), "migrate should keep its path and independent flags"
