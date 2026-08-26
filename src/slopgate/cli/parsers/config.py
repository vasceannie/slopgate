from __future__ import annotations

import argparse
from typing import cast

from slopgate._argparse_types import SubparserRegistry
from slopgate.cli.commands import (
    cmd_config_allow_skill_directories,
    cmd_config_init,
    cmd_config_path,
    cmd_config_show,
)
from slopgate.constants import METADATA_PATH

def _add_config_parsers(sub: SubparserRegistry) -> None:
    """Register configuration management commands."""
    config_parser = sub.add_parser("config", help="Configuration management")
    config_sub = cast(
        SubparserRegistry, config_parser.add_subparsers(dest="config_command")
    )
    _add_command_parser(
        config_sub,
        "show",
        help_text="Show effective configuration",
        func=cmd_config_show,
    )
    init = _add_command_parser(
        config_sub,
        "init",
        help_text="Create config from defaults",
        func=cmd_config_init,
    )
    _ = init.add_argument("--force", action="store_true")
    _add_command_parser(
        config_sub,
        "allow-skill-directories",
        help_text="Allow .claude/skills/ while preserving other protected paths",
        func=cmd_config_allow_skill_directories,
    )
    _add_command_parser(
        config_sub,
        METADATA_PATH,
        help_text="Print config file path",
        func=cmd_config_path,
    )


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


add_command_parser = _add_command_parser
add_config_parsers = _add_config_parsers
