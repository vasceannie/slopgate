"""Parsers for offline eval, hook-log stats, and config migration commands."""

from __future__ import annotations

import argparse
from collections.abc import Iterable

from slopgate._argparse_types import SubparserRegistry
from slopgate.cli._migrate import cmd_migrate
from slopgate.cli.commands import cmd_eval, cmd_stats

from .config import add_command_parser, add_path_command_parser

_EVAL_FLAGS = (
    ("--pretty", "Pretty-print JSON summary"),
    ("--verbose", "Include per-case result rows in the JSON output"),
    (
        "--include-label-only",
        "Also evaluate label_only rows (empty input / non-PreToolUse)",
    ),
)
_MIGRATE_FLAGS = (
    ("--force", "Replace existing ~/.config/slopgate when migrating user config"),
    ("--user-only", "Only migrate user config and OpenCode plugin"),
    ("--repo-only", "Only migrate repo slopgate.toml and disable sentinels"),
)
_STATS_FINGERPRINT_OPTIONS = (
    ("--baseline-policy", "Select the baseline effective-policy fingerprint"),
    ("--candidate-policy", "Select the candidate effective-policy fingerprint"),
    ("--baseline-guidance", "Select the baseline guidance fingerprint"),
    ("--candidate-guidance", "Select the candidate guidance fingerprint"),
)


def _add_flags(
    parser: argparse.ArgumentParser, flags: Iterable[tuple[str, str]]
) -> None:
    for option, help_text in flags:
        _ = parser.add_argument(option, action="store_true", help=help_text)


def add_eval_parser(sub: SubparserRegistry) -> None:
    eval_parser = add_command_parser(
        sub,
        "eval",
        help_text="Evaluate a redacted L1 JSONL attempt-case pack",
        func=cmd_eval,
    )
    _ = eval_parser.add_argument(
        "--pack",
        required=True,
        help="Path to L1 eval JSONL (slopdata or tests/fixtures/eval)",
    )
    _ = eval_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max cases to evaluate",
    )
    _add_flags(eval_parser, _EVAL_FLAGS)
    _ = eval_parser.add_argument(
        "--overlay-out",
        default=None,
        help="Write current-engine sidecar JSONL keyed by case_id (does not rewrite the pack)",
    )


def add_maintenance_parsers(sub: SubparserRegistry) -> None:
    from slopgate.cli.changed_tests_parser import add_changed_test_parser

    stats = add_command_parser(
        sub, "stats", help_text="Analyze hook activity logs", func=cmd_stats
    )
    _ = stats.add_argument("--log")
    _ = stats.add_argument("--days", type=int)
    _ = stats.add_argument("--json", action="store_true")
    for option, help_text in _STATS_FINGERPRINT_OPTIONS:
        _ = stats.add_argument(option, type=str, metavar="HASH", help=help_text)
    _ = stats.add_argument(
        "--cohort",
        action="append",
        default=[],
        metavar="DIM=VALUE",
        help="Restrict comparisons to one cohort dimension value (repeatable)",
    )

    add_changed_test_parser(sub)

    migrate = add_path_command_parser(
        sub,
        "migrate",
        help_text="Migrate legacy slopgate config and quality_gate.toml to slopgate",
        func=cmd_migrate,
    )
    _ = migrate.add_argument("--dry-run", action="store_true")
    _add_flags(migrate, _MIGRATE_FLAGS)
