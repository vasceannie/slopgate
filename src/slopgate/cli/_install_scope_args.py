from __future__ import annotations

import argparse

from slopgate.constants import (
    INSTALL_SCOPE_BOTH,
    INSTALL_SCOPE_PROJECT,
    INSTALL_SCOPE_USER,
)


def add_install_scope_arguments(
    parser: argparse.ArgumentParser, *, help_text: str
) -> None:
    _ = parser.add_argument(
        "--install-scope",
        "--cursor-scope",
        dest="install_scope",
        choices=(INSTALL_SCOPE_USER, INSTALL_SCOPE_PROJECT, INSTALL_SCOPE_BOTH),
        default=INSTALL_SCOPE_USER,
        help=help_text,
    )
    _ = parser.add_argument(
        "--project-root",
        default="",
        help="Project root for --install-scope project/both (default: current directory)",
    )
