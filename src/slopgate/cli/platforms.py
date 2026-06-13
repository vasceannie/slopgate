from __future__ import annotations

import argparse

from slopgate.constants import LINT_SCOPE_ALL, UNKNOWN_VALUE

VALID_PLATFORMS = ("claude", "codex", "opencode", "cursor")
RUNTIME_PLATFORMS = (*VALID_PLATFORMS, UNKNOWN_VALUE)
INSTALL_TARGETS = (*VALID_PLATFORMS, LINT_SCOPE_ALL)
PLATFORM_HELP = (
    f"Target platform. Choices: {', '.join(RUNTIME_PLATFORMS)} "
    f"(default: {UNKNOWN_VALUE})"
)


def add_platform_argument(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument(
        "--platform",
        choices=RUNTIME_PLATFORMS,
        default=UNKNOWN_VALUE,
        help=PLATFORM_HELP,
    )


__all__ = [
    "INSTALL_TARGETS",
    "PLATFORM_HELP",
    "RUNTIME_PLATFORMS",
    "VALID_PLATFORMS",
    "add_platform_argument",
]
