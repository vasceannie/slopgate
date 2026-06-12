"""Windows scheduled-task helpers for suite auto-update."""

from __future__ import annotations

import subprocess
from pathlib import Path

from slopgate.installer._suite_autoupdate_types import (
    AUTOUPDATE_MARKER,
    SchedulerPlan,
    WINDOWS_TASK_NAME,
)


def scheduler_file_is_owned(path: Path) -> bool:
    content = path.read_text(encoding="utf-8", errors="replace")
    marker_line = f"# {AUTOUPDATE_MARKER}"
    plist_marker = f"<!-- {AUTOUPDATE_MARKER} -->"
    return any(
        line.strip() in {marker_line, plist_marker} for line in content.splitlines()[:3]
    )


def remove_windows_task_by_name(dry_run: bool = False) -> bool:
    """Delete the Slopgate auto-update scheduled task by name if it exists.
    Returns True if the task was found and removed, False otherwise."""
    query = subprocess.run(
        ["schtasks", "/Query", "/TN", WINDOWS_TASK_NAME],
        check=False,
        capture_output=True,
        text=True,
    )
    if query.returncode != 0:
        return False
    if dry_run:
        print(f"Would delete scheduled task: {WINDOWS_TASK_NAME}")
        return True
    delete = subprocess.run(
        ["schtasks", "/Delete", "/F", "/TN", WINDOWS_TASK_NAME],
        check=False,
        capture_output=True,
        text=True,
    )
    if delete.returncode != 0:
        print(
            f"Warning: could not delete scheduled task {WINDOWS_TASK_NAME}: "
            f"{delete.stderr.strip()}"
        )
    else:
        print(f"Removed scheduled task: {WINDOWS_TASK_NAME}")
    return delete.returncode == 0


def prepare_windows_task_replacement(plan: SchedulerPlan) -> int:
    if plan.kind != "windows-schtasks":
        return 0
    remove_windows_task_by_name()
    return 0
