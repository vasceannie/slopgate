"""Lint CLI entrypoint and re-exports for tests."""

from __future__ import annotations

import argparse
from pathlib import Path

from slopgate.cli._lint_commands import (
    _discover_project_root,
    _lint_baseline,
    _lint_check,
    _lint_freeze,
    _lint_init,
    _lint_strict,
    _lint_test_integrity,
    _lint_update,
)
from slopgate.cli.lint_report import (
    BASELINE_DISABLED_MESSAGE,
    LintGateMode,
    _LintRunTotals,
    _TallyInput,
    _LintFiles,
    _print_collector_results,
    _print_lint_header,
    _print_lint_summary,
    _tally_rule,
)

_LintGateMode = LintGateMode

__all__ = [
    "BASELINE_DISABLED_MESSAGE",
    "_discover_project_root",
    "_lint_check",
    "_lint_freeze",
    "_lint_strict",
    "_LintFiles",
    "_LintRunTotals",
    "_print_collector_results",
    "_print_lint_header",
    "_print_lint_summary",
    "_TallyInput",
    "_tally_rule",
    "cmd_lint",
]


def cmd_lint(args: argparse.Namespace) -> int:
    raw_lint_command = getattr(args, "lint_command", None)
    lint_command = raw_lint_command if isinstance(raw_lint_command, str) else "check"
    raw_path = getattr(args, "path", ".")
    path_value = raw_path if isinstance(raw_path, str) and raw_path else "."
    root = Path(path_value).resolve()
    dispatch = {
        "baseline": _lint_baseline,
        "freeze": _lint_freeze,
        "init": _lint_init,
    }
    if lint_command == "check":
        raw_details = getattr(args, "details", False)
        return _lint_check(
            Path.cwd(),
            details=raw_details if isinstance(raw_details, bool) else False,
        )
    if lint_command == "strict":
        raw_details = getattr(args, "details", False)
        return _lint_strict(
            Path.cwd(),
            details=raw_details if isinstance(raw_details, bool) else False,
        )
    if lint_command == "test-integrity":
        raw_details = getattr(args, "details", False)
        return _lint_test_integrity(
            Path.cwd(),
            details=raw_details if isinstance(raw_details, bool) else False,
        )
    handler = dispatch.get(lint_command)
    if handler is not None:
        return handler(root)
    if lint_command == "update":
        raw_dry_run = getattr(args, "dry_run", False)
        return _lint_update(
            _discover_project_root(root),
            dry_run=raw_dry_run if isinstance(raw_dry_run, bool) else False,
        )
    return 1
