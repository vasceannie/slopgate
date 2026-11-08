"""Selected-scope Pi package removal with recognized file cleanup."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from slopgate.constants import INSTALL_SCOPE_PROJECT, INSTALL_SCOPE_USER
from slopgate.installer._shared import shell_command
from slopgate.installer.native.commands import (
    REMOVE_SUBCOMMAND,
    NativeCommandError,
    native_executable_available,
)
from slopgate.installer.native.model import LegacyRefusal, NativeRequest
from slopgate.installer.native.packages import native_host_root
from slopgate.installer.native.pi.commands import (
    pi_scope_command,
    run_pi_command,
)
from slopgate.installer.native.pi.cutover import PiCutover
from slopgate.installer.native.pi.identity import PI_EXECUTABLE
from slopgate.installer.native.pi.package import PI_PACKAGE_NAME
from slopgate.installer.native.pi.settings import (
    PackageEntry,
    registered_entry,
)

__all__ = ["uninstall_pi_package"]


def _package_root() -> Path:
    return native_host_root("pi") / "package"


@dataclass(frozen=True, slots=True)
class _UninstallContext:
    request: NativeRequest
    cutover: PiCutover
    entries: dict[str, PackageEntry | None]
    native_available: bool


def _preflight(
    request: NativeRequest, cutover: PiCutover
) -> dict[str, PackageEntry | None] | None:
    try:
        if not request.root.is_dir():
            raise LegacyRefusal(f"Project root does not exist: {request.root}")
        cutover.preflight()
        return {
            scope: registered_entry(scope, request.root, _package_root())
            for scope in request.scopes
        }
    except (LegacyRefusal, OSError, ValueError) as exc:
        print(str(exc))
        return None


def _print_plan(context: _UninstallContext) -> None:
    request, cutover, entries = context.request, context.cutover, context.entries
    for scope in request.scopes:
        if entries[scope] is None:
            continue
        if not context.native_available:
            print(
                f"pi was not found on PATH; cannot remove registered package ({scope} scope)"
            )
            continue
        argv = pi_scope_command(REMOVE_SUBCOMMAND, _package_root(), scope)
        print(f"Would run: {shell_command(argv)} (cwd: {request.root})")
    print("Would verify with: pi list and Pi settings packages")
    for line in cutover.describe():
        print(line)


def _remove_registration(request: NativeRequest, scope: str) -> None:
    argv = pi_scope_command(REMOVE_SUBCOMMAND, _package_root(), scope)
    _ = run_pi_command(argv, request)
    if registered_entry(scope, request.root, _package_root()) is not None:
        raise NativeCommandError(
            f"{PI_PACKAGE_NAME} remains registered ({scope} scope)"
        )
    print(f"Removed {PI_PACKAGE_NAME} ({scope} scope)")


def _remove_scope(context: _UninstallContext, scope: str) -> int:
    entry = context.entries[scope]
    if entry is not None:
        if not context.native_available:
            print(
                f"pi was not found on PATH; cannot remove registered package ({scope} scope)"
            )
            return context.cutover.remove(scope) or 1
        try:
            _remove_registration(context.request, scope)
        except (NativeCommandError, LegacyRefusal, OSError, ValueError) as exc:
            print(str(exc))
            return 1
    return context.cutover.remove(scope)


def _other_scope(scope: str) -> str:
    if scope == INSTALL_SCOPE_USER:
        return INSTALL_SCOPE_PROJECT
    return INSTALL_SCOPE_USER


def _report_other_scope(request: NativeRequest) -> None:
    if len(request.scopes) != 1:
        return
    other = _other_scope(request.scopes[0])
    try:
        entry = registered_entry(other, request.root, _package_root())
    except (LegacyRefusal, OSError, ValueError):
        return
    if entry is not None:
        print(f"Pi {PI_PACKAGE_NAME} remains registered in {other} scope")


def uninstall_pi_package(request: NativeRequest) -> int:
    """Remove selected native registrations and recognized direct-file artifacts."""
    cutover = PiCutover(request)
    entries = _preflight(request, cutover)
    if entries is None:
        return 1
    context = _UninstallContext(
        request, cutover, entries, native_executable_available(PI_EXECUTABLE)
    )
    if request.dry_run:
        _print_plan(context)
        return 0
    status = 0
    for scope in request.scopes:
        scope_status = _remove_scope(context, scope)
        if scope_status != 0:
            status = scope_status
            if entries[scope] is not None and context.native_available:
                return status
    _report_other_scope(request)
    return status
