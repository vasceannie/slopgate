"""Search CLI subcommand argument specifications."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from slopgate.search.config import DEFAULT_SKILL_NAME

CommandFunc = Callable[[argparse.Namespace], int]


class SearchCommands(Protocol):
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
class ArgumentSpec:
    name: str
    action: str | None = None
    nargs: str | None = None
    choices: tuple[str, ...] | None = None
    default: str | None = None


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    help_text: str
    func: CommandFunc
    arguments: tuple[ArgumentSpec, ...] = ()


def _index_command_specs(commands: SearchCommands) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "models",
            "list available embedding models",
            commands.cmd_models,
            (
                ArgumentSpec("--all", action="store_true"),
                ArgumentSpec("--json", action="store_true"),
            ),
        ),
        CommandSpec(
            "use",
            "set default model for this repo",
            commands.cmd_use,
            (ArgumentSpec("model"), ArgumentSpec("--force", action="store_true")),
        ),
        CommandSpec(
            "list",
            "list locally known indexes",
            commands.cmd_list,
            (ArgumentSpec("--json", action="store_true"),),
        ),
        CommandSpec(
            "add",
            "index a repository URL",
            commands.cmd_add,
            (
                ArgumentSpec("repo"),
                ArgumentSpec("--token"),
                ArgumentSpec("--token-env"),
            ),
        ),
        CommandSpec(
            "query",
            "search indexed repositories",
            commands.cmd_search,
            (ArgumentSpec("query", nargs=argparse.REMAINDER),),
        ),
    )


def _maintenance_command_specs(commands: SearchCommands) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "remove",
            "remove an index",
            commands.cmd_remove,
            (ArgumentSpec("target"), ArgumentSpec("--force", action="store_true")),
        ),
        CommandSpec(
            "sync",
            "sync indexes with upstream",
            commands.cmd_sync,
            (ArgumentSpec("targets", nargs="*"),),
        ),
        CommandSpec(
            "reindex",
            "remove and rebuild an index",
            commands.cmd_reindex,
            (ArgumentSpec("target"),),
        ),
        CommandSpec(
            "completions",
            "print shell completions",
            commands.cmd_completions,
            (ArgumentSpec("shell", choices=("bash", "zsh")),),
        ),
    )


def command_specs(commands: SearchCommands) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec("doctor", "check runtime config and endpoint", commands.cmd_doctor),
        *_index_command_specs(commands),
        *_maintenance_command_specs(commands),
    )


def init_argument_specs() -> tuple[ArgumentSpec, ...]:
    return (
        ArgumentSpec("--provider", choices=("litellm", "ollama")),
        ArgumentSpec("--base-url"),
        ArgumentSpec("--model"),
        ArgumentSpec("--api-key-env"),
        ArgumentSpec("--api-key-value"),
        ArgumentSpec("--binary", default="islands-ollama"),
        ArgumentSpec("--islands-config"),
        ArgumentSpec("--integration", choices=("none", "skill", "opencode-tool")),
        ArgumentSpec(
            "--skill-target", choices=("claude", "opencode", "both"), default="both"
        ),
        ArgumentSpec("--skill-name", default=DEFAULT_SKILL_NAME),
        ArgumentSpec("--opencode-plugin-path"),
        ArgumentSpec("--opencode-config"),
        ArgumentSpec("--force", action="store_true"),
    )
