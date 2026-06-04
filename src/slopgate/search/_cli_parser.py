"""Argparse construction for vibeforcer search commands."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol, cast

from vibeforcer._argparse_types import SubparserRegistry
from vibeforcer.search.config import DEFAULT_SKILL_NAME

CommandFunc = Callable[[argparse.Namespace], int]

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


class _SearchCommands(Protocol):
    cmd_init: CommandFunc
    cmd_doctor: CommandFunc
    cmd_models: CommandFunc
    cmd_use: CommandFunc
    cmd_list: CommandFunc
    cmd_add: CommandFunc
    cmd_search: CommandFunc
    cmd_remove: CommandFunc
    cmd_sync: CommandFunc
    cmd_reindex: CommandFunc
    cmd_completions: CommandFunc


@dataclass(frozen=True, slots=True)
class _ArgumentSpec:
    name: str
    action: str | None = None
    nargs: str | None = None
    choices: tuple[str, ...] | None = None
    default: str | None = None


@dataclass(frozen=True, slots=True)
class _CommandSpec:
    name: str
    help_text: str
    func: CommandFunc
    arguments: tuple[_ArgumentSpec, ...] = ()


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
    from vibeforcer.search import cli as commands_module

    commands = cast(_SearchCommands, commands_module)
    _register_init_subcommand(sub, commands.cmd_init)
    for spec in _command_specs(commands):
        _register_subcommand(sub, spec)


def _register_init_subcommand(sub: SubparserRegistry, func: CommandFunc) -> None:
    parser = sub.add_parser("init", help="write wrapper and islands configs")
    _add_arguments(
        parser,
        (
            _ArgumentSpec("--provider", choices=("litellm", "ollama")),
            _ArgumentSpec("--base-url"),
            _ArgumentSpec("--model"),
            _ArgumentSpec("--api-key-env"),
            _ArgumentSpec("--api-key-value"),
            _ArgumentSpec("--binary", default="islands-ollama"),
            _ArgumentSpec("--islands-config"),
            _ArgumentSpec("--integration", choices=("none", "skill", "opencode-tool")),
            _ArgumentSpec("--skill-target", choices=("claude", "opencode", "both"), default="both"),
            _ArgumentSpec("--skill-name", default=DEFAULT_SKILL_NAME),
            _ArgumentSpec("--opencode-plugin-path"),
            _ArgumentSpec("--opencode-config"),
            _ArgumentSpec("--force", action="store_true"),
        ),
    )
    parser.set_defaults(func=func)


def _command_specs(commands: _SearchCommands) -> tuple[_CommandSpec, ...]:
    return (
        _CommandSpec("doctor", "check runtime config and endpoint", commands.cmd_doctor),
        _CommandSpec(
            "models",
            "list available embedding models",
            commands.cmd_models,
            (_ArgumentSpec("--all", action="store_true"), _ArgumentSpec("--json", action="store_true")),
        ),
        _CommandSpec(
            "use",
            "set default model for this repo",
            commands.cmd_use,
            (_ArgumentSpec("model"), _ArgumentSpec("--force", action="store_true")),
        ),
        _CommandSpec("list", "list locally known indexes", commands.cmd_list, (_ArgumentSpec("--json", action="store_true"),)),
        _CommandSpec(
            "add",
            "index a repository URL",
            commands.cmd_add,
            (_ArgumentSpec("repo"), _ArgumentSpec("--token"), _ArgumentSpec("--token-env")),
        ),
        _CommandSpec("query", "search indexed repositories", commands.cmd_search, (_ArgumentSpec("query", nargs=argparse.REMAINDER),)),
        _CommandSpec(
            "remove",
            "remove an index",
            commands.cmd_remove,
            (_ArgumentSpec("target"), _ArgumentSpec("--force", action="store_true")),
        ),
        _CommandSpec("sync", "sync indexes with upstream", commands.cmd_sync, (_ArgumentSpec("targets", nargs="*"),)),
        _CommandSpec("reindex", "remove and rebuild an index", commands.cmd_reindex, (_ArgumentSpec("target"),)),
        _CommandSpec("completions", "print shell completions", commands.cmd_completions, (_ArgumentSpec("shell", choices=("bash", "zsh")),)),
    )


def _register_subcommand(sub: SubparserRegistry, spec: _CommandSpec) -> None:
    parser = sub.add_parser(spec.name, help=spec.help_text)
    _add_arguments(parser, spec.arguments)
    parser.set_defaults(func=spec.func)


def _add_arguments(
    parser: argparse.ArgumentParser,
    specs: Iterable[_ArgumentSpec],
) -> None:
    for spec in specs:
        _add_argument(parser, spec)


def _add_argument(parser: argparse.ArgumentParser, spec: _ArgumentSpec) -> None:
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
