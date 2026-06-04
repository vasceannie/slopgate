"""Lint subcommand argparse wiring."""

from __future__ import annotations

from dataclasses import dataclass

from slopgate._argparse_types import SubparserRegistry
from slopgate.cli.lint import cmd_lint


@dataclass(frozen=True)
class LintAnalysisParserSpec:
    name: str
    help_text: str
    description: str
    details_help: str
    lint_command: str


def _add_lint_analysis_parser(
    lint_sub: SubparserRegistry,
    spec: LintAnalysisParserSpec,
) -> None:
    from slopgate.cli import parsers as core

    parser = lint_sub.add_parser(
        spec.name,
        help=spec.help_text,
        description=spec.description,
    )
    core._add_details_argument(parser, help_text=spec.details_help)
    parser.set_defaults(func=cmd_lint, lint_command=spec.lint_command)


def _add_lint_analysis_parsers(lint_sub: SubparserRegistry) -> None:
    _add_lint_analysis_parser(
        lint_sub,
        LintAnalysisParserSpec(
            name="check",
            help_text="Lint the current project root, including test-integrity checks",
            description=(
                "Lint the current project root, including test-integrity checks. "
                "No path argument is accepted."
            ),
            details_help=(
                "Show extended violation locations, signatures, and repair prognosis"
            ),
            lint_command="check",
        ),
    )
    _add_lint_analysis_parser(
        lint_sub,
        LintAnalysisParserSpec(
            name="strict",
            help_text="Commit gate: fail if any violation exists (not just NEW)",
            description=(
                "Lint the current project root and fail when any violation is present. "
                "Use for git pre-commit; agent stop hooks should use `lint check` instead."
            ),
            details_help=(
                "Show extended violation locations, signatures, and repair prognosis"
            ),
            lint_command="strict",
        ),
    )
    _add_lint_analysis_parser(
        lint_sub,
        LintAnalysisParserSpec(
            name="test-integrity",
            help_text="Scan tests for weak assertions and schema-bypass fakes",
            description="Scan project tests for weak assertions and integration gaps.",
            details_help="Show contextual repair guidance for each suspicious test",
            lint_command="test-integrity",
        ),
    )


@dataclass(frozen=True)
class _LintPathSubcommandSpec:
    name: str
    help_text: str
    description: str
    lint_command: str


def _add_lint_path_subcommand(
    lint_sub: SubparserRegistry,
    spec: _LintPathSubcommandSpec,
) -> None:
    from slopgate.cli import parsers as core

    parser = lint_sub.add_parser(
        spec.name,
        help=spec.help_text,
        description=spec.description,
    )
    core._add_optional_path_argument(parser)
    parser.set_defaults(func=cmd_lint, lint_command=spec.lint_command)


_LINT_PATH_SUBCOMMANDS = (
    _LintPathSubcommandSpec(
        name="freeze",
        help_text="One-time baseline snapshot when rules are empty",
        description=(
            "Write current lint findings to baselines.json. "
            "Only allowed while the baseline rules map is empty."
        ),
        lint_command="freeze",
    ),
    _LintPathSubcommandSpec(
        name="baseline",
        help_text="Disabled: repo-wide rebaselining is not allowed",
        description="Disabled: repo-wide rebaselining is not allowed",
        lint_command="baseline",
    ),
)


def _add_lint_path_subcommands(lint_sub: SubparserRegistry) -> None:
    for spec in _LINT_PATH_SUBCOMMANDS:
        _add_lint_path_subcommand(lint_sub, spec)


def _add_lint_init_parser(lint_sub: SubparserRegistry) -> None:
    from slopgate.cli import parsers as core

    init = lint_sub.add_parser("init", help="Scaffold slopgate.toml")
    core._add_optional_path_argument(init)
    init.set_defaults(func=cmd_lint, lint_command="init")


def _add_lint_update_parser(lint_sub: SubparserRegistry) -> None:
    from slopgate.cli import parsers as core

    update = lint_sub.add_parser("update", help="Add missing config keys")
    core._add_optional_path_argument(update)
    core._add_dry_run_argument(update)
    update.set_defaults(func=cmd_lint, lint_command="update")


def add_lint_parsers(sub: SubparserRegistry) -> None:
    lint = sub.add_parser("lint", help="Batch code quality analysis")
    lint_sub = lint.add_subparsers(dest="lint_command")

    _add_lint_analysis_parsers(lint_sub)
    _add_lint_path_subcommands(lint_sub)
    _add_lint_init_parser(lint_sub)
    _add_lint_update_parser(lint_sub)

    lint.set_defaults(func=cmd_lint, lint_command="check")
