"""Transactional marketplace-plugin install with scope-safe legacy cutover."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from slopgate.constants import INSTALL_SCOPE_PROJECT, INSTALL_SCOPE_USER
from slopgate.installer._shared import UnsafeInstallPathError, shell_command
from slopgate.installer.native.artifacts import remove_empty_directories
from slopgate.installer.native.commands import NativeCommandError
from slopgate.installer.native.marketplace.host import MarketplaceHost
from slopgate.installer.native.marketplace.state import (
    Preflight,
    compensation_commands,
    marketplace_command,
    marketplace_registered,
    preflight,
    registration_for,
    run_checked,
    scope_commands,
    verification_problem,
)
from slopgate.installer.native.model import (
    LegacyCutover,
    LegacyRefusal,
    NativeRequest,
    Registration,
)
from slopgate.installer.native.packages import (
    PackagePlan,
    StagingError,
    StagingSnapshot,
    restore_staging,
    snapshot_staging,
    write_staging,
)
from slopgate.installer.native.settings_guard import (
    SettingsGuard,
    capture_guards,
    restore_guards,
)
from slopgate.util import logger

__all__ = ["install_marketplace_host"]


class _InstallFailure(Exception):
    """An install step failed; the message is shown before rollback."""


@dataclass(slots=True)
class _InstallRun:
    host: MarketplaceHost
    plan: PackagePlan
    request: NativeRequest
    cutover: LegacyCutover
    state: Preflight
    staging: StagingSnapshot | None = None
    marketplace_added: bool = False
    marketplace_refreshed: bool = False
    touched: list[str] = field(default_factory=list)
    anchor: Path | None = None
    guards: dict[str, tuple[SettingsGuard, ...]] = field(default_factory=dict)
    marketplace_guards: tuple[SettingsGuard, ...] = ()

    def execute(self) -> None:
        if INSTALL_SCOPE_PROJECT in self.request.scopes:
            self.anchor = self.host.ensure_project_anchor(self.request.root)
        self.cutover.capture()
        self.staging = snapshot_staging(self.plan)
        write_staging(self.plan)
        self._refresh_marketplace()
        for scope in self.request.scopes:
            self._register(scope)
        self._verify()
        for scope in self.request.scopes:
            if self.cutover.remove(scope) != 0:
                raise _InstallFailure(
                    f"Failed to retire legacy {self.host.label} enforcement "
                    f"({scope} scope)"
                )

    def _refresh_marketplace(self) -> None:
        command = marketplace_command(self.host, self.plan, self.state)
        if command is None:
            return
        if self.state.marketplace_present:
            self.marketplace_refreshed = True
            _ = run_checked(self.host, command, self.request.root)
            return
        self.marketplace_guards = capture_guards(
            self.host.native_settings(INSTALL_SCOPE_USER, self.request.root)
        )
        cwd = self.host.commands.marketplace_add_cwd(
            self.plan.entry_root, self.request.root
        )
        try:
            _ = run_checked(self.host, command, cwd)
        except NativeCommandError:
            # Only a registration that actually landed needs removing; a
            # rejected add must not trigger a removal that itself fails.
            self.marketplace_added = marketplace_registered(
                self.host, self.request.root
            )
            if not self.marketplace_added:
                restore_guards(self.marketplace_guards)
            raise
        self.marketplace_added = True

    def _register(self, scope: str) -> None:
        prior = self.state.prior[scope]
        commands = scope_commands(self.host, scope, (prior, self.plan.version))
        if commands:
            if prior is None:
                self.guards[scope] = capture_guards(
                    self.host.native_settings(scope, self.request.root)
                )
            self.touched.append(scope)
        for argv in commands:
            _ = run_checked(self.host, argv, self.request.root)

    def _verify(self) -> None:
        for scope in self.request.scopes:
            current = registration_for(self.host, scope, self.request.root)
            problem = verification_problem(
                current, self.state.prior[scope], self.plan.version
            )
            if problem is not None:
                raise _InstallFailure(
                    f"{self.host.label} inventory does not show "
                    f"{self.host.plugin_id} ({scope} scope): {problem}"
                )

    def rollback(self) -> list[str]:
        """Compensate every mutation; return descriptions of incomplete steps.

        Uninstalls need no payload, so they run first; the staged payload is
        restored only once no registration is left depending on it.
        """
        incomplete: list[str] = []
        fresh = _scopes_by_prior(self.touched, self.state.prior, replaced=False)
        self._compensate_scopes(incomplete, fresh)
        self._restore_catalog_state(incomplete)
        if self.marketplace_added:
            _guarded(incomplete, "marketplace removal", self._remove_marketplace)
        if self.cutover.restore() != 0:
            incomplete.append("legacy artifacts")
        if self.anchor is not None and remove_empty_directories((self.anchor,)) != 0:
            incomplete.append(f"project anchor {self.anchor}")
        return incomplete

    def _compensate_scopes(self, incomplete: list[str], scopes: list[str]) -> None:
        for scope in scopes:
            _guarded(
                incomplete, f"{scope} registration", lambda s=scope: self._compensate(s)
            )

    def _restore_catalog_state(self, incomplete: list[str]) -> None:
        """Restore staged files, then re-register what needs the prior catalog.

        Nothing here runs once any earlier step is incomplete: install/replace
        commands would read a stale or partial catalog, and a kept payload is
        the best state for registrations that could not be compensated.
        """
        replaced = _scopes_by_prior(self.touched, self.state.prior, replaced=True)
        skipped = [f"{scope} registration skipped" for scope in replaced]
        refresh_skipped = (
            ["marketplace refresh skipped"] if self.marketplace_refreshed else []
        )
        if incomplete:
            if self.staging is not None:
                incomplete.append("staged marketplace files kept: registrations remain")
            incomplete.extend(refresh_skipped + skipped)
            return
        if self.staging is not None and restore_staging(self.staging) != 0:
            incomplete.append("staged marketplace files")
            incomplete.extend(refresh_skipped + skipped)
            return
        if self.marketplace_refreshed:
            _guarded(incomplete, "marketplace refresh", self._refresh_catalog)
            if incomplete:
                incomplete.extend(skipped)
                return
        self._compensate_scopes(incomplete, replaced)

    def _refresh_catalog(self) -> None:
        argv = self.host.commands.marketplace_update()
        _ = run_checked(self.host, argv, self.request.root)

    def _compensate(self, scope: str) -> None:
        root = self.request.root
        current = registration_for(self.host, scope, root)
        prior = self.state.prior[scope]
        for argv in compensation_commands(self.host, scope, (prior, current)):
            _ = run_checked(self.host, argv, root)
        if prior is None:
            restore_guards(self.guards[scope])

    def _remove_marketplace(self) -> None:
        if self.host.registrations(self.request.root):
            return
        argv = self.host.commands.marketplace_remove()
        _ = run_checked(self.host, argv, self.request.root)
        restore_guards(self.marketplace_guards)


def _scopes_by_prior(
    touched: list[str],
    prior: dict[str, Registration | None],
    *,
    replaced: bool,
) -> list[str]:
    """Touched scopes in rollback order that did (replaced) or did not (fresh) exist."""
    return [
        scope for scope in reversed(touched) if (prior[scope] is not None) == replaced
    ]


def _guarded(incomplete: list[str], label: str, action: Callable[[], None]) -> None:
    try:
        action()
    except (OSError, NativeCommandError, LegacyRefusal, ValueError) as exc:
        incomplete.append(f"{label}: {exc}")


def _print_dry_run(
    host: MarketplaceHost,
    plan: PackagePlan,
    request: NativeRequest,
    context: tuple[Preflight, LegacyCutover, str],
) -> None:
    state, cutover, binary = context
    print("Installation mode: native plugin")
    print(f"Plugin: {host.plugin_id}")
    print(f"Scope: {', '.join(request.scopes)} (project root: {request.root})")
    if INSTALL_SCOPE_PROJECT in request.scopes:
        anchor_action = host.project_anchor_action(request.root)
        if anchor_action is not None:
            print(anchor_action)
    print(f"Would stage {len(plan.files)} files at {plan.entry_root}")
    print(f"Version: {plan.version}")
    command = marketplace_command(host, plan, state)
    if command is not None:
        print(f"Would run: {shell_command(command)}")
    for scope in request.scopes:
        for argv in scope_commands(host, scope, (state.prior[scope], plan.version)):
            print(f"Would run: {shell_command(argv)} (cwd: {request.root})")
    print(f"Would verify with: {host.list_command}")
    for line in cutover.describe():
        print(line)
    print(f"Binary: {binary}")


def _state_label(registration: Registration | None) -> str:
    if registration is None or registration.enabled is None:
        return "not recorded"
    return "enabled" if registration.enabled else "disabled"


def _print_success(
    host: MarketplaceHost, plan: PackagePlan, context: tuple[NativeRequest, str]
) -> None:
    request, binary = context
    print("Installation mode: native plugin")
    print(f"Plugin: {host.plugin_id}")
    for scope in request.scopes:
        registration = registration_for(host, scope, request.root)
        print(
            f"Scope: {scope}: version {plan.version}, "
            f"native state {_state_label(registration)}"
        )
        if registration is not None and registration.enabled is False:
            print(
                f"Registered but disabled ({scope} scope): enforcement is not "
                f"active until re-enabled through {host.label}'s plugin manager"
            )
    print(f"Native listing: {host.list_command}")
    print(f"Binary: {binary}")
    print(host.activation_note)


def install_marketplace_host(
    host: MarketplaceHost, request: NativeRequest, binary: str
) -> int:
    """Stage, register, verify and cut over to a native marketplace plugin."""
    plan = host.build_plan(binary)
    cutover = host.legacy_cutover(request)
    state = preflight(host, plan, request, cutover)
    if state is None:
        return 1
    if request.dry_run:
        _print_dry_run(host, plan, request, (state, cutover, binary))
        return 0
    run = _InstallRun(host, plan, request, cutover, state)
    try:
        run.execute()
    except (
        _InstallFailure,
        NativeCommandError,
        StagingError,
        LegacyRefusal,
        UnsafeInstallPathError,
        OSError,
    ) as exc:
        print(str(exc))
        incomplete = run.rollback()
        if incomplete:
            print("Incomplete rollback: " + "; ".join(incomplete))
        return 1
    _print_success(host, plan, (request, binary))
    logger.info(
        "installer native registration complete",
        platform=host.platform,
        scopes=",".join(request.scopes),
    )
    return 0
