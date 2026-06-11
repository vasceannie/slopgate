"""Lint CLI entrypoint and re-exports for tests."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Protocol

from slopgate.cli.lint.commands import (
    discover_project_root,
    lint_baseline,
    lint_check,
    lint_freeze,
    lint_init,
    lint_strict,
    lint_test_integrity,
    lint_update,
)
from slopgate.cli.lint.report import (
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
    "lint_init",
    "lint_strict",
    "lint_update",
    "lint_baseline",
    "lint_test_integrity",
    "LintFiles",
    "LintRunTotals",
    "print_collector_results",
    "print_lint_header",
    "print_lint_summary",
    "TallyInput",
    "tally_rule",
    "cmd_lint",
]


class _LintScanHandler(Protocol):
    def __call__(self, root: Path, /, *, details: bool = False) -> int: ...


class _LintPathHandler(Protocol):
    def __call__(self, root: Path, /) -> int: ...


def _details_enabled(args: argparse.Namespace) -> bool:
    raw_details = getattr(args, "details", False)
    return raw_details if isinstance(raw_details, bool) else False


def _requested_root(args: argparse.Namespace) -> Path:
    raw_path = getattr(args, "path", ".")
    path_value = raw_path if isinstance(raw_path, str) and raw_path else "."
    return Path(path_value).resolve()


SCAN_COMMANDS: dict[str, _LintScanHandler] = {
    "check": lint_check,
    "strict": lint_strict,
    "test-integrity": lint_test_integrity,
}

PATH_COMMANDS: dict[str, _LintPathHandler] = {
    "baseline": lint_baseline,
    "freeze": lint_freeze,
    "init": lint_init,
}


def _scan_command_name(name: str) -> str | None:
    if name in SCAN_COMMANDS:
        return name
    return None


def _path_command_name(name: str) -> str | None:
    if name in PATH_COMMANDS:
        return name
    return None


def _run_scan_command(args: argparse.Namespace, name: str) -> int:
    handler = SCAN_COMMANDS[name]
    return handler(Path.cwd(), details=_details_enabled(args))


def _run_path_command(args: argparse.Namespace, name: str) -> int:
    handler = PATH_COMMANDS[name]
    return handler(_requested_root(args))


def _run_update_command(args: argparse.Namespace) -> int:
    raw_dry_run = getattr(args, "dry_run", False)
    return lint_update(
        discover_project_root(_requested_root(args)),
        dry_run=raw_dry_run if isinstance(raw_dry_run, bool) else False,
    )


def cmd_lint(args: argparse.Namespace) -> int:
    raw_lint_command = getattr(args, "lint_command", None)
    lint_command = raw_lint_command if isinstance(raw_lint_command, str) else "check"
    scan_command = _scan_command_name(lint_command)
    if scan_command is not None:
        return _run_scan_command(args, scan_command)
    path_command = _path_command_name(lint_command)
    if path_command is not None:
        return _run_path_command(args, path_command)
    if lint_command == "update":
        return _run_update_command(args)
    return 1
