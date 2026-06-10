"""Shared scheduler plan types and markers for suite auto-update."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

AUTOUPDATE_MARKER = "Slopgate auto-update managed file"
WINDOWS_TASK_NAME = "Slopgate Auto Update"


@dataclass(frozen=True)
class SchedulerPlan:
    """OS-specific auto-update scheduler plan."""

    kind: str
    target_path: Path
    content: str
    enable_command: list[str] | None
