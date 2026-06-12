"""Argparse construction for slopgate search commands."""

from __future__ import annotations
import argparse
from collections.abc import Iterable
from typing import cast
from slopgate._argparse_types import SubparserRegistry
from slopgate.search.cli.command_specs import (
    ArgumentSpec,
    CommandFunc,
    CommandSpec,
    command_specs,
    init_argument_specs,
)

_SEARCH_DESCRIPTION = "Semantic code search via islands-ollama."
SEARCH_SUBCOMMANDS = (
    "init",
    "doctor",
    "models",
    "use",
    "list",
    "add",
    "query",
    "remove",
    "sync",
    "reindex",
    "completions",
)


def build_search_parser(
    subparsers: SubparserRegistry | None = None,
) -> argparse.ArgumentParser:
    """Build the ``search`` subcommand parser."""
    parser = _create_search_root(subparsers)
    sub = parser.add_subparsers(dest="search_command")
    _register_all_subcommands(sub)
    return parser


def _create_search_root(
    subparsers: SubparserRegistry | None,
) -> argparse.ArgumentParser:
    if subparsers is not None:
        return subparsers.add_parser(
            "search",
            help="Semantic code search via islands",
            description=_SEARCH_DESCRIPTION,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
    return argparse.ArgumentParser(
        prog="isx",
        description=_SEARCH_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def _register_all_subcommands(sub: SubparserRegistry) -> None:
    from slopgate.search import cli
    from slopgate.search.cli.command_specs import SearchCommands

    commands = cast(SearchCommands, cli)
    _register_init_subcommand(sub, commands.cmd_init)
    for spec in command_specs(commands):
        _register_subcommand(sub, spec)


def _register_init_subcommand(sub: SubparserRegistry, func: CommandFunc) -> None:
    parser = sub.add_parser("init", help="write wrapper and islands configs")
    _add_arguments(parser, init_argument_specs())
    parser.set_defaults(func=func)


def _register_subcommand(sub: SubparserRegistry, spec: CommandSpec) -> None:
    parser = sub.add_parser(spec.name, help=spec.help_text)
    _add_arguments(parser, spec.arguments)
    parser.set_defaults(func=spec.func)


def _add_arguments(
    parser: argparse.ArgumentParser, specs: Iterable[ArgumentSpec]
) -> None:
    for spec in specs:
        _add_argument(parser, spec)


def _add_argument(parser: argparse.ArgumentParser, spec: ArgumentSpec) -> None:
    if spec.action is not None:
        _ = parser.add_argument(spec.name, action=spec.action)
        return
    if spec.nargs is not None:
        _ = parser.add_argument(spec.name, nargs=spec.nargs)
        return
    if spec.choices is not None and spec.default is not None:
        _ = parser.add_argument(spec.name, choices=spec.choices, default=spec.default)
        return
    if spec.choices is not None:
        _ = parser.add_argument(spec.name, choices=spec.choices)
        return
    if spec.default is not None:
        _ = parser.add_argument(spec.name, default=spec.default)
        return
    _ = parser.add_argument(spec.name)
