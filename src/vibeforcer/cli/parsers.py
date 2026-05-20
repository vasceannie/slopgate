from __future__ import annotations

import argparse
from dataclasses import dataclass

from vibeforcer._argparse_types import SubparserRegistry

from vibeforcer.cli.commands import (
    PLATFORM_HELP,
    VALID_PLATFORMS,
    cmd_check,
    cmd_config_init,
    cmd_config_path,
    cmd_config_show,
    cmd_enroll,
    cmd_handle,
    cmd_handle_async,
    cmd_install,
    cmd_replay,
    cmd_stats,
    cmd_test,
    cmd_uninstall,
    cmd_version,
)
from vibeforcer.cli.lint import cmd_lint


@dataclass(frozen=True)
class LintAnalysisParserSpec:
    name: str
    help_text: str
    description: str
    details_help: str
    lint_command: str


def _add_platform_argument(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument(
        "--platform", choices=VALID_PLATFORMS, default="claude", help=PLATFORM_HELP
    )


def _add_optional_path_argument(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("path", nargs="?", default=".")


def _add_dry_run_argument(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--dry-run", action="store_true")


def _add_details_argument(parser: argparse.ArgumentParser, *, help_text: str) -> None:
    _ = parser.add_argument(
        "--details",
        "--verbose",
        dest="details",
        action="store_true",
        help=help_text,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vibeforcer",
        description="Global CLI guardrails engine for AI coding agents",
    )
    _ = parser.add_argument(
        "--version", action="store_true", help="Print version and exit"
    )
    sub = parser.add_subparsers(dest="command")
    _add_core_parsers(sub)
    _add_config_parsers(sub)
    _add_lint_parsers(sub)

    from vibeforcer.search.cli import build_search_parser

    _ = build_search_parser(sub)
    version = sub.add_parser("version", help="Print version")
    version.set_defaults(func=cmd_version)
    return parser


def _add_command_parser(
    sub: SubparserRegistry,
    name: str,
    *,
    help_text: str,
    func: object,
) -> argparse.ArgumentParser:
    parser = sub.add_parser(name, help=help_text)
    parser.set_defaults(func=func)
    return parser


def _add_path_command_parser(
    sub: SubparserRegistry,
    name: str,
    *,
    help_text: str,
    func: object,
) -> argparse.ArgumentParser:
    parser = _add_command_parser(sub, name, help_text=help_text, func=func)
    _add_optional_path_argument(parser)
    return parser


def _add_platform_install_parser(
    sub: SubparserRegistry,
    name: str,
    *,
    help_text: str,
    func: object,
) -> None:
    parser = _add_command_parser(sub, name, help_text=help_text, func=func)
    _ = parser.add_argument("platform", choices=VALID_PLATFORMS)
    _add_dry_run_argument(parser)


def _add_core_parsers(sub: SubparserRegistry) -> None:
    handle = _add_command_parser(
        sub, "handle", help_text="Read hook payload from stdin", func=cmd_handle
    )
    _add_platform_argument(handle)

    _add_command_parser(
        sub, "handle-async", help_text="Run async post-edit jobs", func=cmd_handle_async
    )
    _add_path_command_parser(
        sub, "check", help_text="Check quality gate for a repo", func=cmd_check
    )

    enroll = _add_path_command_parser(
        sub, "enroll", help_text="Enroll a repo in quality gate enforcement", func=cmd_enroll
    )
    _ = enroll.add_argument(
        "--no-worktrees",
        action="store_true",
        help="Only enroll the main repo root",
    )

    replay = _add_command_parser(
        sub, "replay", help_text="Replay a saved payload", func=cmd_replay
    )
    _ = replay.add_argument("--payload", required=True)
    _ = replay.add_argument("--pretty", action="store_true")
    _add_platform_argument(replay)

    _add_platform_install_parser(
        sub, "install", help_text="Install hooks for a platform", func=cmd_install
    )
    _add_platform_install_parser(
        sub, "uninstall", help_text="Remove hooks from a platform", func=cmd_uninstall
    )

    stats = _add_command_parser(
        sub, "stats", help_text="Analyze hook activity logs", func=cmd_stats
    )
    _ = stats.add_argument("--log")
    _ = stats.add_argument("--days", type=int)
    _ = stats.add_argument("--json", action="store_true")

    _add_command_parser(sub, "test", help_text="Run self-test / smoke test", func=cmd_test)


def _add_config_parsers(sub: SubparserRegistry) -> None:
    config_parser = sub.add_parser("config", help="Configuration management")
    config_sub = config_parser.add_subparsers(dest="config_command")

    _add_command_parser(
        config_sub, "show", help_text="Show effective configuration", func=cmd_config_show
    )
    init = _add_command_parser(
        config_sub, "init", help_text="Create config from defaults", func=cmd_config_init
    )
    _ = init.add_argument("--force", action="store_true")
    _add_command_parser(
        config_sub, "path", help_text="Print config file path", func=cmd_config_path
    )


def _add_lint_analysis_parser(
    lint_sub: SubparserRegistry,
    spec: LintAnalysisParserSpec,
) -> None:
    parser = lint_sub.add_parser(
        spec.name,
        help=spec.help_text,
        description=spec.description,
    )
    _add_details_argument(parser, help_text=spec.details_help)
    parser.set_defaults(func=cmd_lint, lint_command=spec.lint_command)


def _add_lint_analysis_parsers(lint_sub: SubparserRegistry) -> None:
    _add_lint_analysis_parser(
        lint_sub,
        LintAnalysisParserSpec(
            name="check",
            help_text="Lint the current project root",
            description=(
                "Lint the current project root. This command intentionally accepts no "
                "file or directory argument so agents cannot bypass full-project checks."
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
            name="test-integrity",
            help_text=(
                "Scan tests for weak assertions, mock theater, and schema-bypass fakes"
            ),
            description=(
                "Scan the current project tests for bad-test-efficacy indicators: weak "
                "presence assertions, mock-only proofs, schema bypasses, hand-built "
                "payload drift, over-mocked integration tests, untested production code, "
                "missing integration seams, Hypothesis candidates, and obsolete tests."
            ),
            details_help="Show contextual repair guidance for each suspicious test",
            lint_command="test-integrity",
        ),
    )


def _add_lint_baseline_parser(lint_sub: SubparserRegistry) -> None:
    baseline = lint_sub.add_parser(
        "baseline",
        help="Disabled: repo-wide rebaselining is not allowed",
        description="Disabled: repo-wide rebaselining is not allowed",
    )
    _add_optional_path_argument(baseline)
    baseline.set_defaults(func=cmd_lint, lint_command="baseline")


def _add_lint_init_parser(lint_sub: SubparserRegistry) -> None:
    init = lint_sub.add_parser("init", help="Scaffold quality_gate.toml")
    _add_optional_path_argument(init)
    init.set_defaults(func=cmd_lint, lint_command="init")


def _add_lint_update_parser(lint_sub: SubparserRegistry) -> None:
    update = lint_sub.add_parser("update", help="Add missing config keys")
    _add_optional_path_argument(update)
    _add_dry_run_argument(update)
    update.set_defaults(func=cmd_lint, lint_command="update")


def _add_lint_parsers(sub: SubparserRegistry) -> None:
    lint = sub.add_parser("lint", help="Batch code quality analysis")
    lint_sub = lint.add_subparsers(dest="lint_command")

    _add_lint_analysis_parsers(lint_sub)
    _add_lint_baseline_parser(lint_sub)
    _add_lint_init_parser(lint_sub)
    _add_lint_update_parser(lint_sub)

    lint.set_defaults(func=cmd_lint, lint_command="check")
