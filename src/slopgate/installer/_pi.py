"""Pi native package installer support."""

from __future__ import annotations

from pathlib import Path

from slopgate.installer.native.commands import NativeCommandError
from slopgate.installer.native.entry import run_native_install
from slopgate.installer.native.model import NativeRequest, make_request_or_report
from slopgate.installer.native.pi import install_pi_package, uninstall_pi_package
from slopgate.installer.native.pi.legacy import (
    PI_OWNERSHIP_MARKERS,
    pi_extension_has_owned_slopgate,
    pi_project_extension_path,
    pi_user_extension_path,
    render_pi_extension,
)

__all__ = [
    "PI_OWNERSHIP_MARKERS",
    "install_pi",
    "pi_extension_has_owned_slopgate",
    "pi_project_extension_path",
    "pi_user_extension_path",
    "render_pi_extension",
    "uninstall_pi",
]


def _install_pi_with_errors(request: NativeRequest, binary: str) -> int:
    try:
        return install_pi_package(request, binary)
    except (NativeCommandError, OSError, ValueError) as exc:
        print(str(exc))
        return 1


def install_pi(
    dry_run: bool = False, *, scope: str = "user", project_root: Path | None = None
) -> int:
    """Install the staged package and retire recognized loose-extension files."""
    return run_native_install(scope, project_root, dry_run, _install_pi_with_errors)


def uninstall_pi(
    dry_run: bool = False, *, scope: str = "user", project_root: Path | None = None
) -> int:
    """Remove the selected native package registration and loose-extension files."""
    request = make_request_or_report(scope, project_root, dry_run)
    if request is None:
        return 1
    try:
        return uninstall_pi_package(request)
    except (NativeCommandError, OSError, ValueError) as exc:
        print(str(exc))
        return 1
