"""CLI parser registration for packaged Slopgate bundle commands."""

from __future__ import annotations

import argparse
from typing import cast

from slopgate._argparse_types import SubparserRegistry
from slopgate.installer._install_scope import (
    INSTALL_SCOPE_BOTH,
    INSTALL_SCOPE_PROJECT,
    INSTALL_SCOPE_USER,
)
from slopgate.cli.commands import VALID_PLATFORMS
from slopgate.cli.commands_bundle import cmd_bundle_sync_prompts


def _add_dry_run_argument(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--dry-run", action="store_true")


def _add_install_scope_arguments(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument(
        "--install-scope",
        "--cursor-scope",
        dest="install_scope",
        choices=(INSTALL_SCOPE_USER, INSTALL_SCOPE_PROJECT, INSTALL_SCOPE_BOTH),
        default=INSTALL_SCOPE_USER,
        help=(
            "Prompt target: user config dir, project prompt file, or both; "
            "project scope uses CLAUDE.md for Claude and AGENTS.md for other harnesses"
        ),
    )
    _ = parser.add_argument(
        "--project-root",
        default="",
        help="Project root for --install-scope project/both (default: current directory)",
    )


def _add_prompt_target_arguments(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument(
        "--only",
        choices=("all", *VALID_PLATFORMS),
        default="all",
        help="Prompt target to sync (default: all)",
    )
    _add_install_scope_arguments(parser)


def add_bundle_parsers(sub: SubparserRegistry) -> None:
    """Register commands for package-managed prompt fragments and shared assets."""

    bundle = sub.add_parser(
        "bundle",
        help="Manage Slopgate packaged prompt fragments and shared agent assets",
    )
    bundle_sub = cast(SubparserRegistry, bundle.add_subparsers(dest="bundle_command"))
    sync = bundle_sub.add_parser(
        "sync-prompts",
        help="Append or refresh Slopgate managed routing blocks in harness markdown prompts",
    )
    sync.set_defaults(func=cmd_bundle_sync_prompts)
    _add_dry_run_argument(sync)
    _ = sync.add_argument(
        "--remove",
        "--uninstall",
        action="store_true",
        help="Remove only the Slopgate managed routing block from prompt files",
    )
    _add_prompt_target_arguments(sync)

    uninstall = bundle_sub.add_parser(
        "uninstall-prompts",
        help="Remove Slopgate managed routing blocks from harness markdown prompts",
    )
    uninstall.set_defaults(func=cmd_bundle_sync_prompts, remove=True)
    _add_dry_run_argument(uninstall)
    _add_prompt_target_arguments(uninstall)
