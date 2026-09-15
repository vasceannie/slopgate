"""Argument wiring for repair-gate subcommands."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from slopgate._argparse_types import SubparserRegistry

from ._commands import cmd_repair_clear, cmd_repair_status, cmd_repair_verify


def _add_repair_scope_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--worktree")


def _add_repair_subcommand(
    repair_sub: SubparserRegistry,
    name: str,
    help_text: str,
    func: Callable[[argparse.Namespace], int],
) -> argparse.ArgumentParser:
    """Register one repair subcommand with its scope arguments."""
    parser = repair_sub.add_parser(name, help=help_text)
    _add_repair_scope_arguments(parser)
    parser.set_defaults(func=func)
    return parser


def add_repair_parsers(sub: SubparserRegistry) -> None:
    repair = sub.add_parser("repair", help="Inspect or verify repair-required state")
    repair_sub = repair.add_subparsers(dest="repair_command", required=True)
    _add_repair_subcommand(
        repair_sub, "status", "Print current repair state", cmd_repair_status
    )
    verify = _add_repair_subcommand(
        repair_sub,
        "verify",
        "Run clean verification and clear a generation",
        cmd_repair_verify,
    )
    verify.add_argument("--generation", required=True)
    clear = _add_repair_subcommand(
        repair_sub,
        "clear",
        "Clear one pending generation by exact generation without verification",
        cmd_repair_clear,
    )
    clear.add_argument("--generation", required=True)
