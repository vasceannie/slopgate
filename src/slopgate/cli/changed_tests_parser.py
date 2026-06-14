"""Parser registration for the ``slopgate test`` changed-test workflow."""

from __future__ import annotations

import argparse

from slopgate._argparse_types import SubparserRegistry
from slopgate.cli.commands import cmd_test


def add_changed_test_parser(sub: SubparserRegistry) -> None:
    parser = sub.add_parser(
        "test",
        help="Run tests impacted by changed Python source files",
    )
    parser.set_defaults(func=cmd_test)
    _ = parser.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="Print selected test paths without running them",
    )
    changed_source = parser.add_mutually_exclusive_group()
    _ = changed_source.add_argument(
        "--smoke",
        action="store_true",
        help="Run Slopgate's internal hook smoke suite instead of project tests",
    )
    _ = changed_source.add_argument(
        "--since",
        help="Git ref used to select changed files (default: HEAD)",
    )
    _ = changed_source.add_argument(
        "--files",
        nargs="+",
        help="Explicit repo-relative changed source paths",
    )
    _ = parser.add_argument(
        "--runner",
        help=(
            "Test runner command prefix; default: "
            "python -m pytest -n auto -v --tb=short"
        ),
    )
    _ = parser.add_argument("runner_args", nargs=argparse.REMAINDER)


__all__ = ["add_changed_test_parser"]
