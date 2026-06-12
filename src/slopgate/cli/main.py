from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from typing import cast

from slopgate.cli.parsers import build_parser
from slopgate.constants import EXIT_KEYBOARD_INTERRUPT


CommandFunc = Callable[[argparse.Namespace], int]


def _string_attr(args: argparse.Namespace, name: str) -> str | None:
    value = getattr(args, name, None)
    return value if isinstance(value, str) and value else None


def _bool_attr(args: argparse.Namespace, name: str) -> bool:
    value = getattr(args, name, False)
    return value if isinstance(value, bool) else False


def _callable_attr(args: argparse.Namespace, name: str) -> CommandFunc | None:
    value = getattr(args, name, None)
    return cast(CommandFunc, value) if callable(value) else None


def _string_list_attr(args: argparse.Namespace, name: str) -> list[str] | None:
    raw_value = getattr(args, name, None)
    if not isinstance(raw_value, list):
        return None
    raw_items = cast(list[object], raw_value)
    if not all(isinstance(item, str) for item in raw_items):
        return None
    return cast(list[str], raw_items) or None


def _search_subcommands() -> set[str]:
    from slopgate.search.cli.parser import SEARCH_SUBCOMMANDS

    return set(SEARCH_SUBCOMMANDS)


def _normalize_search_argv(argv: list[str]) -> list[str]:
    """Rewrite bare search queries to the explicit query subcommand."""
    if not argv or argv[0] != "search":
        return argv
    rest = argv[1:]
    if not rest:
        return ["search", "--help"]
    first = rest[0]
    if first.startswith("-") or first in _search_subcommands():
        return argv
    return ["search", "query", *rest]


def _normalize_isx_argv(argv: list[str] | None) -> list[str] | None:
    """Rewrite bare ``isx`` queries to the explicit query subcommand."""
    if argv is None:
        return None
    if not argv:
        return argv
    first = argv[0]
    if first.startswith("-") or first in _search_subcommands():
        return argv
    return ["query", *argv]


def _run_search_func(args: argparse.Namespace) -> int:
    from slopgate.search.config import IsxError

    try:
        func = _callable_attr(args, "func")
        if func is None:
            return 0
        return func(args)
    except IsxError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _run_search_command(args: argparse.Namespace) -> int | None:
    search_cmd = _string_attr(args, "search_command")
    if search_cmd and _callable_attr(args, "func") is not None:
        return _run_search_func(args)
    return None


def _run_default_search_query(args: argparse.Namespace) -> int | None:
    query_args = _string_list_attr(args, "query_args")
    if not query_args:
        return None
    from slopgate.search.cli import cmd_search

    args.query = query_args
    args.func = cmd_search
    return _run_search_func(args)


def _dispatch_search(args: argparse.Namespace) -> int:
    from slopgate.util import logger

    logger.info(
        "cli search dispatch",
        event_name="search",
        service="slopgate.search.cli",
        search_command=getattr(args, "search_command", "unset"),
    )
    result = _run_search_command(args)
    if result is not None:
        return result
    return _run_default_search_query(args) or 0


def _isx_main(argv: list[str] | None = None) -> int:
    from slopgate.search.cli import build_search_parser

    parser = build_search_parser(subparsers=None)
    args = parser.parse_args(_normalize_isx_argv(argv))
    result = _run_search_command(args)
    if result is not None:
        return result

    default_result = _run_default_search_query(args)
    if default_result is not None:
        return default_result

    parser.print_help()
    return 0


def main(argv: list[str] | None = None) -> int:
    prog_name = os.path.basename(sys.argv[0]) if sys.argv else ""
    if prog_name == "isx":
        return _isx_main(argv)

    raw_argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    args = parser.parse_args(_normalize_search_argv(raw_argv))
    if _bool_attr(args, "version"):
        from slopgate.cli.commands import cmd_version

        return cmd_version(args)
    command = _string_attr(args, "command")
    if command is None:
        parser.print_help()
        return 0
    if command == "search":
        return _dispatch_search(args)
    func = _callable_attr(args, "func")
    if func is None:
        _ = parser.parse_args([command, "--help"])
        return 0
    return func(args)


def safe_main(argv: list[str] | None = None) -> int:
    try:
        return main(argv)
    except KeyboardInterrupt:
        return EXIT_KEYBOARD_INTERRUPT
