"""Selected-scope plugin removal with recognized file cleanup."""

from __future__ import annotations

from slopgate.installer._shared import UnsafeInstallPathError, shell_command
from slopgate.installer.native.commands import (
    NativeCommandError,
    native_executable_available,
)
from slopgate.installer.native.marketplace.host import MarketplaceHost
from slopgate.installer.native.marketplace.state import registration_for, run_checked
from slopgate.installer.native.model import LegacyCutover, LegacyRefusal, NativeRequest
from slopgate.installer.native.packages import StagingError

__all__ = ["uninstall_marketplace_host"]


def _print_plan(
    host: MarketplaceHost,
    request: NativeRequest,
    context: tuple[LegacyCutover, bool],
) -> int:
    cutover, native = context
    try:
        for scope in request.scopes:
            if native and registration_for(host, scope, request.root) is not None:
                command = shell_command(host.commands.uninstall(scope))
                print(f"Would run: {command} (cwd: {request.root})")
        for line in cutover.describe():
            print(line)
    except (
        NativeCommandError,
        LegacyRefusal,
        UnsafeInstallPathError,
        OSError,
        StagingError,
    ) as exc:
        print(str(exc))
        return 1
    return 0


def _remove_registration(
    host: MarketplaceHost, request: NativeRequest, scope: str
) -> None:
    if registration_for(host, scope, request.root) is None:
        return
    _ = run_checked(host, host.commands.uninstall(scope), request.root)
    if registration_for(host, scope, request.root) is not None:
        raise NativeCommandError(
            f"{host.plugin_id} is still registered ({scope} scope) after uninstall"
        )
    print(f"Removed {host.plugin_id} ({scope} scope)")


def _remove_scopes(
    host: MarketplaceHost,
    request: NativeRequest,
    context: tuple[LegacyCutover, bool],
) -> int:
    cutover, native = context
    for scope in request.scopes:
        try:
            if native:
                _remove_registration(host, request, scope)
            status = cutover.remove(scope)
        except (
            LegacyRefusal,
            UnsafeInstallPathError,
            OSError,
            NativeCommandError,
            StagingError,
        ) as exc:
            print(str(exc))
            return 1
        if status != 0:
            return status
    return 0


def uninstall_marketplace_host(host: MarketplaceHost, request: NativeRequest) -> int:
    """Remove the selected-scope registration and recognized direct-file artifacts.

    The marketplace and staged payload are kept: another project or scope may
    still reference them, and the native manager owns its own cache cleanup.
    """
    try:
        cutover = host.legacy_cutover(request)
        if not request.root.is_dir():
            raise LegacyRefusal(f"Project root does not exist: {request.root}")
        cutover.preflight()
    except (
        LegacyRefusal,
        UnsafeInstallPathError,
        OSError,
        NativeCommandError,
        StagingError,
    ) as exc:
        print(str(exc))
        return 1
    native = native_executable_available(host.executable)
    if not native:
        print(
            f"{host.executable} was not found on PATH; native registration was not "
            "checked and staged payloads were left in place."
        )
    if request.dry_run:
        return _print_plan(host, request, (cutover, native))
    return _remove_scopes(host, request, (cutover, native))
