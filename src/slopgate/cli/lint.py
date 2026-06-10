"""Lint CLI entrypoint and re-exports for tests."""

from __future__ import annotations

import argparse
from pathlib import Path

from slopgate.cli._lint_commands import (
    discover_project_root,
    lint_baseline,
    lint_check,
    lint_freeze,
    lint_init,
    lint_strict,
    lint_test_integrity,
    lint_update,
)
from slopgate.cli.lint_report import (
    BASELINE_DISABLED_MESSAGE,
    LintGateMode,
    LintRunTotals,
    TallyInput,
    LintFiles,
    print_collector_results,
    print_lint_header,
    print_lint_summary,
    tally_rule,
)

_LintGateMode = LintGateMode

__all__ = [
    "BASELINE_DISABLED_MESSAGE",
    "discover_project_root",
    "lint_check",
    "lint_freeze",
    "lint_strict",
    "LintFiles",
    "LintRunTotals",
    "print_collector_results",
    "print_lint_header",
    "print_lint_summary",
    "TallyInput",
    "tally_rule",
    "cmd_lint",
]


def cmd_lint(args: argparse.Namespace) -> int:
    raw_lint_command = getattr(args, "lint_command", None)
    lint_command = raw_lint_command if isinstance(raw_lint_command, str) else "check"
    raw_path = getattr(args, "path", ".")
    path_value = raw_path if isinstance(raw_path, str) and raw_path else "."
    root = Path(path_value).resolve()
    dispatch = {
        "baseline": lint_baseline,
        "freeze": lint_freeze,
        "init": lint_init,
    }
    if lint_command == "check":
        raw_details = getattr(args, "details", False)
        return lint_check(
            Path.cwd(),
            details=raw_details if isinstance(raw_details, bool) else False,
        )
    if lint_command == "strict":
        raw_details = getattr(args, "details", False)
        return lint_strict(
            Path.cwd(),
            details=raw_details if isinstance(raw_details, bool) else False,
        )
    if lint_command == "test-integrity":
        raw_details = getattr(args, "details", False)
        return lint_test_integrity(
            Path.cwd(),
            details=raw_details if isinstance(raw_details, bool) else False,
        )
    handler = dispatch.get(lint_command)
    if handler is not None:
        return handler(root)
    if lint_command == "update":
        raw_dry_run = getattr(args, "dry_run", False)
        return lint_update(
            discover_project_root(root),
            dry_run=raw_dry_run if isinstance(raw_dry_run, bool) else False,
        )
    return 1
