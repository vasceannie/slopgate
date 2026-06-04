from __future__ import annotations

import argparse

from slopgate._argparse_types import SubparserRegistry

from slopgate.cli._migrate import cmd_migrate
from slopgate.cli.commands import (
    INSTALL_TARGETS,
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
    cmd_install_suite,
    cmd_replay,
    cmd_stats,
    cmd_test,
    cmd_uninstall,
    cmd_update_suite,
    cmd_version,
)
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
        prog="slopgate",
        description="Global CLI guardrails engine for AI coding agents",
    )
    _ = parser.add_argument(
        "--version", action="store_true", help="Print version and exit"
    )
    sub = parser.add_subparsers(dest="command")
    _add_core_parsers(sub)
    _add_config_parsers(sub)
    from slopgate.cli.parsers_lint import add_lint_parsers

    add_lint_parsers(sub)

    from slopgate.search.cli import build_search_parser

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


def _add_install_scope_arguments(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument(
        "--install-scope",
        "--cursor-scope",
        dest="install_scope",
        choices=("user", "project", "both"),
        default="user",
        help=(
            "Hook install target: user config dir, project dir (./.claude, ./.codex, "
            "./.cursor, ./.opencode), or both"
        ),
    )
    _ = parser.add_argument(
        "--project-root",
        default="",
        help="Project root for --install-scope project/both (default: current directory)",
    )


def _add_platform_install_parser(
    sub: SubparserRegistry,
    name: str,
    *,
    help_text: str,
    func: object,
) -> None:
    parser = _add_command_parser(sub, name, help_text=help_text, func=func)
    choices = INSTALL_TARGETS if name in {"install", "uninstall"} else VALID_PLATFORMS
    _ = parser.add_argument("platform", choices=choices)
    _add_dry_run_argument(parser)
    if name == "install":
        _add_suite_update_arguments(parser, include_dry_run=False)
    if name not in {"install", "uninstall"}:
        return
    _ = parser.add_argument(
        "--with-autoupdate",
        action="store_true",
        help="Also install/remove the current OS's periodic GitHub updater",
    )
    _add_install_scope_arguments(parser)
    if name == "uninstall":
        return
    _ = parser.add_argument(
        "--interval-minutes",
        type=int,
        default=3 * 10,
        help="Auto-update polling interval for the native scheduler",
    )


def _add_suite_update_arguments(
    parser: argparse.ArgumentParser, *, include_dry_run: bool = True
) -> None:
    if include_dry_run:
        _add_dry_run_argument(parser)
    _ = parser.add_argument(
        "--source",
        default="git+https://github.com/vasceannie/slopgate.git@master",
        help="Package source used by auto-update clients",
    )
    _ = parser.add_argument(
        "--include-missing",
        action="store_true",
        help="Create hook install sites even when that harness has not been configured yet",
    )


def _add_suite_command_parser(
    sub: SubparserRegistry,
    name: str,
    *,
    help_text: str,
    func: object,
) -> argparse.ArgumentParser:
    parser = _add_command_parser(sub, name, help_text=help_text, func=func)
    _add_suite_update_arguments(parser)
    _add_install_scope_arguments(parser)
    return parser


def _add_suite_parsers(sub: SubparserRegistry) -> None:
    install_suite = _add_suite_command_parser(
        sub,
        "install-suite",
        help_text="Install all detected harness hooks and optionally the auto-updater",
        func=cmd_install_suite,
    )
    _ = install_suite.add_argument(
        "--with-autoupdate",
        action="store_true",
        help="Install the current OS's periodic GitHub updater",
    )
    _ = install_suite.add_argument(
        "--interval-minutes",
        type=int,
        default=3 * 10,
        help="Auto-update polling interval for the native scheduler",
    )

    _ = _add_suite_command_parser(
        sub,
        "update-suite",
        help_text="Update Slopgate from GitHub and refresh detected hook sites",
        func=cmd_update_suite,
    )


def _add_hook_runtime_parsers(sub: SubparserRegistry) -> None:
    handle = _add_command_parser(
        sub, "handle", help_text="Read hook payload from stdin", func=cmd_handle
    )
    _add_platform_argument(handle)

    _add_command_parser(
        sub, "handle-async", help_text="Run async post-edit jobs", func=cmd_handle_async
    )

    replay = _add_command_parser(
        sub, "replay", help_text="Replay a saved payload", func=cmd_replay
    )
    _ = replay.add_argument("--payload", required=True)
    _ = replay.add_argument("--pretty", action="store_true")
    _add_platform_argument(replay)


def _add_repo_enrollment_parsers(sub: SubparserRegistry) -> None:
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


def _add_platform_install_parsers(sub: SubparserRegistry) -> None:
    _add_platform_install_parser(
        sub, "install", help_text="Install hooks for a platform", func=cmd_install
    )
    _add_platform_install_parser(
        sub, "uninstall", help_text="Remove hooks from a platform", func=cmd_uninstall
    )
    _add_suite_parsers(sub)


def _add_maintenance_parsers(sub: SubparserRegistry) -> None:
    stats = _add_command_parser(
        sub, "stats", help_text="Analyze hook activity logs", func=cmd_stats
    )
    _ = stats.add_argument("--log")
    _ = stats.add_argument("--days", type=int)
    _ = stats.add_argument("--json", action="store_true")

    _add_command_parser(sub, "test", help_text="Run self-test / smoke test", func=cmd_test)

    migrate = _add_path_command_parser(
        sub,
        "migrate",
        help_text="Migrate legacy slopgate config and quality_gate.toml to slopgate",
        func=cmd_migrate,
    )
    _ = migrate.add_argument("--dry-run", action="store_true")
    _ = migrate.add_argument(
        "--force",
        action="store_true",
        help="Replace existing ~/.config/slopgate when migrating user config",
    )
    _ = migrate.add_argument(
        "--user-only",
        action="store_true",
        help="Only migrate user config and OpenCode plugin",
    )
    _ = migrate.add_argument(
        "--repo-only",
        action="store_true",
        help="Only migrate repo slopgate.toml and disable sentinels",
    )


def _add_core_parsers(sub: SubparserRegistry) -> None:
    _add_hook_runtime_parsers(sub)
    _add_repo_enrollment_parsers(sub)
    _add_platform_install_parsers(sub)
    _add_maintenance_parsers(sub)


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


