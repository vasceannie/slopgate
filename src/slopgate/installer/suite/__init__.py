"""Installer suite support APIs."""

from __future__ import annotations

from slopgate.installer.suite.autoupdate import (
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DEFAULT_UPDATE_SOURCE,
    build_scheduler_plan,
    install_autoupdate,
    uninstall_autoupdate,
)
from slopgate.installer.suite.autoupdate_types import (
    AUTOUPDATE_MARKER,
    SchedulerPlan,
)

__all__ = [
    "AUTOUPDATE_MARKER",
    "DEFAULT_UPDATE_INTERVAL_MINUTES",
    "DEFAULT_UPDATE_SOURCE",
    "SchedulerPlan",
    "build_scheduler_plan",
    "install_autoupdate",
    "uninstall_autoupdate",
]
