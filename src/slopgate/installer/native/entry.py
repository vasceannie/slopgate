"""Request validation and dispatch for native install entrypoints."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from slopgate.installer._shared import find_binary
from slopgate.installer.native.model import NativeRequest, make_request_or_report

__all__ = ["run_native_install"]


def run_native_install(
    scope: str,
    project_root: Path | None,
    dry_run: bool,
    installer: Callable[[NativeRequest, str], int],
) -> int:
    """Validate CLI input, resolve the binary, then dispatch.

    Exceptions from binary resolution and installation propagate to the caller.
    """
    request = make_request_or_report(scope, project_root, dry_run)
    if request is None:
        return 1
    return installer(request, find_binary())
