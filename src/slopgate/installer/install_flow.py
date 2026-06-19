"""Shared install flow helpers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


def rollback_completed_installs(
    completed: list[Path],
    uninstall: Callable[[Path], int],
) -> None:
    """Best-effort rollback for multi-target installs after a later target fails."""
    for rollback_path in completed:
        _ = uninstall(rollback_path)
