"""Native OMP marketplace installer and prior extension migration."""

from __future__ import annotations

from pathlib import Path

import slopgate.installer._shared
from slopgate.constants import INSTALL_SCOPE_USER
from slopgate.installer._install_scope import (
    ResidualInstallScopeWarning,
    warn_residual_install_scope,
)
from slopgate.installer._omp_support import (
    ArtifactSnapshot,
    MANIFEST_TEXT,
    OMP_OWNERSHIP_MARKERS,
    OmpSiteSnapshot,
    omp_extension_has_owned_slopgate,
)
from slopgate.installer.native.commands import NativeCommandError
from slopgate.installer.native.marketplace import (
    install_marketplace_host,
    uninstall_marketplace_host,
)
from slopgate.installer.native.model import make_request
from slopgate.installer.native.omp import (
    OMP_LIST_COMMAND,
    OMP_PLUGIN_ID,
    OMP_PLUGIN_NAME,
    OmpMarketplaceCommands,
    OmpMarketplaceHost,
    render_omp_extension,
)
from slopgate.installer.native.omp_legacy import (
    OmpLegacyCutover,
    omp_agent_dir,
    omp_project_extension_path,
    omp_user_extension_path,
)


def install_omp(
    dry_run: bool = False,
    *,
    scope: str = INSTALL_SCOPE_USER,
    project_root: Path | None = None,
) -> int:
    """Install or refresh Slopgate through OMP's native plugin manager."""
    try:
        request = make_request(scope, project_root, dry_run=dry_run)
    except ValueError as exc:
        print(str(exc))
        return 1
    binary = slopgate.installer._shared.find_binary()
    try:
        return install_marketplace_host(OmpMarketplaceHost(), request, binary)
    except (NativeCommandError, OSError, ValueError) as exc:
        print(str(exc))
        return 1


def uninstall_omp(
    dry_run: bool = False,
    *,
    scope: str = INSTALL_SCOPE_USER,
    project_root: Path | None = None,
) -> int:
    """Remove selected OMP registration and recognized prior extension files."""
    try:
        request = make_request(scope, project_root, dry_run=dry_run)
    except ValueError as exc:
        print(str(exc))
        return 1
    try:
        status = uninstall_marketplace_host(OmpMarketplaceHost(), request)
    except (NativeCommandError, OSError, ValueError) as exc:
        print(str(exc))
        return 1
    if status == 0 and not dry_run:
        root = request.root
        warn_residual_install_scope(
            ResidualInstallScopeWarning(
                platform_label="OMP",
                scope=scope,
                user_path=omp_user_extension_path(),
                project_path=omp_project_extension_path(root),
                project_root=project_root,
                has_owned=omp_extension_has_owned_slopgate,
            )
        )
    return status


__all__ = [
    "ArtifactSnapshot",
    "MANIFEST_TEXT",
    "OMP_LIST_COMMAND",
    "OMP_OWNERSHIP_MARKERS",
    "OMP_PLUGIN_ID",
    "OMP_PLUGIN_NAME",
    "OmpLegacyCutover",
    "OmpMarketplaceCommands",
    "OmpMarketplaceHost",
    "OmpSiteSnapshot",
    "install_omp",
    "omp_agent_dir",
    "omp_extension_has_owned_slopgate",
    "omp_project_extension_path",
    "omp_user_extension_path",
    "render_omp_extension",
    "uninstall_omp",
]
