"""Read-only preflight and command planning for marketplace installs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from slopgate.constants import INSTALL_SCOPE_PROJECT
from slopgate.installer._shared import UnsafeInstallPathError, shell_command
from slopgate.installer.native.commands import (
    NativeCommandError,
    native_executable_available,
    run_native_command,
)
from slopgate.installer.native.marketplace.host import MarketplaceHost
from slopgate.installer.native.model import (
    LegacyCutover,
    LegacyRefusal,
    NativeRequest,
    Registration,
)
from slopgate.installer.native.packages import (
    MARKETPLACE_NAME,
    PackagePlan,
    StagingError,
    check_staging_owned,
    staging_is_current,
)

__all__ = [
    "Preflight",
    "compensation_commands",
    "marketplace_command",
    "marketplace_registered",
    "preflight",
    "registration_for",
    "run_checked",
    "scope_commands",
    "verification_problem",
]


@dataclass(slots=True)
class Preflight:
    """Native state observed before any mutation."""

    marketplace_present: bool
    catalog_current: bool
    prior: dict[str, Registration | None]


def run_checked(host: MarketplaceHost, argv: list[str], cwd: Path) -> str:
    """Run a native command and raise ``NativeCommandError`` on nonzero exit."""
    completed = run_native_command(argv, cwd=cwd, platform=host.platform)
    if completed.returncode != 0:
        streams = (completed.stderr.strip(), completed.stdout.strip())
        detail = " | ".join(text for text in streams if text)
        raise NativeCommandError(
            f"{shell_command(argv)} exited {completed.returncode}: {detail}"
        )
    return completed.stdout


def registration_for(
    host: MarketplaceHost, scope: str, root: Path
) -> Registration | None:
    """Find this plugin's registration for exactly one scope/project association."""
    for registration in host.registrations(root):
        if registration.scope != scope:
            continue
        if scope == INSTALL_SCOPE_PROJECT and (
            registration.project is None or registration.project.resolve() != root
        ):
            continue
        return registration
    return None


def marketplace_registered(host: MarketplaceHost, root: Path) -> bool:
    """Whether the Slopgate marketplace is registered; unknown counts as yes.

    Used after a failed add so rollback removes only what actually landed, yet
    never leaks a registration it cannot rule out.
    """
    try:
        return MARKETPLACE_NAME in host.marketplace_sources(root)
    except NativeCommandError:
        return True


def _same_source(source: str, entry_root: Path, added_from: Path) -> bool:
    """Whether a reported source is ``entry_root``.

    A host may report the relative source it was added with (``./marketplace``),
    which names a directory relative to where the add ran, not to this process.
    """
    try:
        return (added_from / source).resolve() == entry_root.resolve()
    except OSError:
        return False


def _read_state(
    host: MarketplaceHost, plan: PackagePlan, request: NativeRequest
) -> Preflight:
    source = host.marketplace_sources(request.root).get(MARKETPLACE_NAME)
    added_from = host.commands.marketplace_add_cwd(plan.entry_root, request.root)
    if source is not None and not _same_source(source, plan.entry_root, added_from):
        raise LegacyRefusal(
            f"Refusing to use existing {host.label} marketplace "
            f"'{MARKETPLACE_NAME}' with a different source: {source} "
            f"(expected {plan.entry_root})"
        )
    prior = {
        scope: registration_for(host, scope, request.root) for scope in request.scopes
    }
    return Preflight(
        marketplace_present=source is not None,
        catalog_current=staging_is_current(plan),
        prior=prior,
    )


def preflight(
    host: MarketplaceHost,
    plan: PackagePlan,
    request: NativeRequest,
    cutover: LegacyCutover,
) -> Preflight | None:
    """Validate everything read-only; print the reason and return None on refusal."""
    try:
        if not request.root.is_dir():
            raise LegacyRefusal(f"Project root does not exist: {request.root}")
        check_staging_owned(plan)
        cutover.preflight()
        if not native_executable_available(host.executable):
            raise NativeCommandError(
                f"{host.executable} was not found on PATH; install the {host.label} "
                "CLI. Existing enforcement was left unchanged."
            )
        issue = (
            host.project_anchor_issue(request.root)
            if INSTALL_SCOPE_PROJECT in request.scopes
            else None
        )
        if issue:
            raise LegacyRefusal(issue)
        return _read_state(host, plan, request)
    except (
        StagingError,
        LegacyRefusal,
        UnsafeInstallPathError,
        OSError,
        NativeCommandError,
    ) as exc:
        print(str(exc))
        return None


def marketplace_command(
    host: MarketplaceHost, plan: PackagePlan, state: Preflight
) -> list[str] | None:
    """The one marketplace add/update command this install needs, if any."""
    if not state.marketplace_present:
        return host.commands.marketplace_add(plan.entry_root)
    if not state.catalog_current:
        return host.commands.marketplace_update()
    return None


def scope_commands(
    host: MarketplaceHost,
    scope: str,
    prior_and_version: tuple[Registration | None, str],
) -> list[list[str]]:
    """Install/replace commands for one scope; empty when already current."""
    prior, version = prior_and_version
    if prior is None:
        return host.commands.install(scope, None)
    if prior.version != version:
        return host.commands.replace(scope, prior)
    return []


def compensation_commands(
    host: MarketplaceHost,
    scope: str,
    prior_and_current: tuple[Registration | None, Registration | None],
) -> list[list[str]]:
    """Commands that return a scope's registration to its pre-install state."""
    prior, current = prior_and_current
    if prior is None:
        return [host.commands.uninstall(scope)] if current is not None else []
    if current is None:
        return host.commands.install(scope, prior)
    if current.version != prior.version or current.enabled != prior.enabled:
        return host.commands.replace(scope, prior)
    return []


def verification_problem(
    current: Registration | None, prior: Registration | None, version: str
) -> str | None:
    """Why a post-install inventory entry is unacceptable, or None."""
    if current is None:
        return "no registration found"
    if current.version != version:
        return f"version {current.version} (expected {version})"
    if (
        prior is not None
        and prior.enabled is not None
        and current.enabled != prior.enabled
    ):
        return (
            f"native enabled state {current.enabled} "
            f"does not match previous state {prior.enabled}"
        )
    return None
