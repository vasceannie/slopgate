"""Parser registration for hook runtime commands."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from slopgate._argparse_types import SubparserRegistry

PlatformArgumentAdder = Callable[[argparse.ArgumentParser], None]


class CommandParserFactory(Protocol):
    def __call__(
        self,
        sub: SubparserRegistry,
        name: str,
        *,
        help_text: str,
        func: object,
    ) -> argparse.ArgumentParser: ...


@dataclass(frozen=True, slots=True)
class HookRuntimeParserRegistration:
    add_command_parser: CommandParserFactory
    add_platform_argument: PlatformArgumentAdder
    help_by_name: Mapping[str, str]
    func_by_name: Mapping[str, object]


def add_hook_runtime_parsers(
    sub: SubparserRegistry,
    registration: HookRuntimeParserRegistration,
) -> None:
    from slopgate.cli.first_write_contract import add_contract_parser
    from slopgate.cli.recovery import add_recovery_parser

    handle = registration.add_command_parser(
        sub,
        "handle",
        help_text=registration.help_by_name["handle"],
        func=registration.func_by_name["handle"],
    )
    registration.add_platform_argument(handle)

    daemon = registration.add_command_parser(
        sub,
        "daemon",
        help_text=registration.help_by_name["daemon"],
        func=registration.func_by_name["daemon"],
    )
    _ = daemon.add_argument("--socket")
    _ = daemon.add_argument("--max-requests", type=int)
    _ = daemon.add_argument("--workers", type=positive_int)
    _ = daemon.add_argument("--serial", action="store_true")

    registration.add_command_parser(
        sub,
        "handle-async",
        help_text=registration.help_by_name["handle-async"],
        func=registration.func_by_name["handle-async"],
    )

    replay = registration.add_command_parser(
        sub,
        "replay",
        help_text=registration.help_by_name["replay"],
        func=registration.func_by_name["replay"],
    )
    _ = replay.add_argument("--payload", required=True)
    _ = replay.add_argument("--pretty", action="store_true")
    registration.add_platform_argument(replay)
    add_contract_parser(sub)
    add_recovery_parser(sub)


def positive_int(raw_value: str) -> int:
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


__all__ = [
    "CommandParserFactory",
    "HookRuntimeParserRegistration",
    "add_hook_runtime_parsers",
    "positive_int",
]
