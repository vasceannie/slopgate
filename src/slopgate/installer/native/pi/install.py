"""Transactional installation of Pi's native local package."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from slopgate.constants import INSTALL_SCOPE_PROJECT, INSTALL_SCOPE_USER
from slopgate.installer._shared import UnsafeInstallPathError, shell_command
from slopgate.installer.native.commands import (
    LIST_SUBCOMMAND,
    REMOVE_SUBCOMMAND,
    NativeCommandError,
    native_executable_available,
)
from slopgate.installer.native.model import LegacyRefusal, NativeRequest
from slopgate.installer.native.packages import (
    PackagePlan,
    StagingError,
    StagingSnapshot,
    check_staging_owned,
    restore_staging,
    snapshot_staging,
    staging_is_current,
    write_staging,
)
from slopgate.installer.native.pi.commands import (
    PI_MINIMUM_VERSION_TEXT,
    PI_VERSION_COMMAND,
    pi_scope_command,
    require_supported_pi_version,
    run_pi_command,
)
from slopgate.installer.native.pi.cutover import PiCutover
from slopgate.installer.native.pi.identity import PI_EXECUTABLE
from slopgate.installer.native.pi.legacy import pi_template_path
from slopgate.installer.native.pi.package import build_pi_plan
from slopgate.installer.native.pi.settings import (
    PackageEntry,
    package_entries,
    registered_entry,
    settings_path,
)
from slopgate.installer.native.settings_guard import (
    NativeSettingsFile,
    SettingsGuard,
    capture_guards,
    restore_guards,
)

__all__ = ["install_pi_package"]

_LIST_COMMAND = f"{PI_EXECUTABLE} {LIST_SUBCOMMAND}"


@dataclass(slots=True)
class _PiState:
    """Read-only preflight state for all requested scopes."""

    entries: dict[str, PackageEntry | None]


@dataclass(slots=True)
class _InstallContext:
    """Mutable transaction state required for accurate rollback."""

    request: NativeRequest
    plan: PackagePlan
    cutover: PiCutover
    prior: _PiState
    staging: StagingSnapshot | None = None
    guards: dict[str, tuple[SettingsGuard, ...]] = field(default_factory=dict)
    attempted_scopes: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _DryRunContext:
    """Read-only install preview inputs."""

    plan: PackagePlan
    request: NativeRequest
    state: _PiState
    cutover: PiCutover
    binary: str


class _InstallFailure(RuntimeError):
    """A Pi native operation failed and needs transaction rollback."""


def _read_state(plan: PackagePlan, request: NativeRequest) -> _PiState:
    entries = {
        scope: registered_entry(scope, request.root, plan.entry_root)
        for scope in request.scopes
    }
    return _PiState(entries)


def _preflight(
    plan: PackagePlan, request: NativeRequest, cutover: PiCutover
) -> _PiState | None:
    try:
        if not request.root.is_dir():
            raise LegacyRefusal(f"Project root does not exist: {request.root}")
        check_staging_owned(plan)
        cutover.preflight()
        for scope in request.scopes:
            _ = package_entries(settings_path(scope, request.root), scope, request.root)
        if not native_executable_available(PI_EXECUTABLE):
            raise NativeCommandError(
                "pi was not found on PATH; install the Pi CLI. Existing enforcement "
                "was left unchanged."
            )
        if not request.dry_run:
            require_supported_pi_version(request)
        return _read_state(plan, request)
    except (
        LegacyRefusal,
        NativeCommandError,
        StagingError,
        UnsafeInstallPathError,
        OSError,
        ValueError,
    ) as exc:
        print(str(exc))
        return None


def _verify_pi_list(stdout: str, source_root: Path) -> bool:
    target = source_root.resolve()
    for line in stdout.splitlines():
        candidate = Path(line.strip())
        if not candidate.is_absolute():
            continue
        try:
            if candidate.resolve() == target:
                return True
        except (OSError, RuntimeError):
            continue
    return False


def _verify_scope(context: _InstallContext, scope: str) -> None:
    current = registered_entry(scope, context.request.root, context.plan.entry_root)
    if current is None:
        raise _InstallFailure(
            f"Pi settings do not register {context.plan.entry_root} ({scope} scope)"
        )
    if scope == INSTALL_SCOPE_USER:
        output = run_pi_command([PI_EXECUTABLE, LIST_SUBCOMMAND], context.request)
        if not _verify_pi_list(output, context.plan.entry_root):
            raise _InstallFailure(
                f"pi list does not report {context.plan.entry_root} for user scope"
            )


class _InstallRun:
    """Execute and compensate one Pi package installation transaction."""

    def __init__(self, context: _InstallContext) -> None:
        self._context = context

    def execute(self) -> None:
        context = self._context
        context.cutover.capture()
        if not staging_is_current(context.plan):
            context.staging = snapshot_staging(context.plan)
            write_staging(context.plan)
        for scope in context.request.scopes:
            self._register(scope)
        for scope in context.request.scopes:
            _verify_scope(context, scope)
        for scope in context.request.scopes:
            if context.cutover.remove(scope) != 0:
                raise _InstallFailure(
                    f"Failed to retire legacy Pi enforcement ({scope} scope)"
                )

    def _register(self, scope: str) -> None:
        context = self._context
        if context.prior.entries[scope] is not None:
            return
        context.guards[scope] = capture_guards(
            (
                NativeSettingsFile(
                    settings_path(scope, context.request.root), frozenset({"packages"})
                ),
            )
        )
        context.attempted_scopes.append(scope)
        _ = run_pi_command(
            pi_scope_command("install", context.plan.entry_root, scope),
            context.request,
        )

    def rollback(self) -> list[str]:
        """Compensate every mutation; return descriptions of incomplete steps.

        Registrations are compensated before the staged package is restored: a
        registration that could not be removed must keep a loadable payload.
        """
        context = self._context
        incomplete: list[str] = []
        for scope in reversed(context.attempted_scopes):
            _guarded(
                incomplete,
                f"{scope} package registration",
                lambda selected=scope: self._compensate(selected),
            )
        if context.staging is not None:
            if incomplete:
                incomplete.append(
                    "staged Pi package kept so remaining registrations stay loadable"
                )
            elif restore_staging(context.staging) != 0:
                incomplete.append("staged Pi package")
        if context.cutover.restore() != 0:
            incomplete.append("legacy Pi artifacts")
        return incomplete

    def _compensate(self, scope: str) -> None:
        context = self._context
        current = registered_entry(scope, context.request.root, context.plan.entry_root)
        if current is not None:
            _ = run_pi_command(
                pi_scope_command(REMOVE_SUBCOMMAND, context.plan.entry_root, scope),
                context.request,
            )
            if (
                registered_entry(scope, context.request.root, context.plan.entry_root)
                is not None
            ):
                raise NativeCommandError(
                    f"Pi package remains registered ({scope} scope)"
                )
        restore_guards(context.guards[scope])


def _guarded(incomplete: list[str], label: str, action: Callable[[], None]) -> None:
    try:
        action()
    except (OSError, NativeCommandError, LegacyRefusal, ValueError) as exc:
        incomplete.append(f"{label}: {exc}")


def _print_dry_run(context: _DryRunContext) -> None:
    plan, request, state, cutover, binary = (
        context.plan,
        context.request,
        context.state,
        context.cutover,
        context.binary,
    )
    print("Installation mode: native package")
    version_check = shell_command(list(PI_VERSION_COMMAND))
    print(
        f"Would require Pi {PI_MINIMUM_VERSION_TEXT} or newer "
        f"(checked with: {version_check})"
    )
    print(f"Package source: {plan.entry_root}")
    print(f"Scope: {', '.join(request.scopes)} (project root: {request.root})")
    print(
        f"Would stage {len(plan.files)} files at {plan.entry_root} (version {plan.version})"
    )
    for scope in request.scopes:
        if state.entries[scope] is None:
            command = shell_command(pi_scope_command("install", plan.entry_root, scope))
            print(f"Would run: {command} (cwd: {request.root})")
        else:
            print(
                f"Already registered in {scope} settings; native install will be skipped"
            )
    print(f"Would verify user scope with: {_LIST_COMMAND}")
    for scope in request.scopes:
        print(f"Settings inventory: {settings_path(scope, request.root)} packages")
    for line in cutover.describe():
        print(line)
    print(f"Binary: {binary}")


def _state_label(entry: PackageEntry | None) -> str:
    if entry is None:
        return "not registered"
    if entry.filtered:
        return "registered with resource filters"
    return "registered"


def _print_success(plan: PackagePlan, request: NativeRequest, binary: str) -> None:
    print("Installation mode: native package")
    print(f"Package source: {plan.entry_root}")
    for scope in request.scopes:
        entry = registered_entry(scope, request.root, plan.entry_root)
        print(
            f"Scope: {scope}: version {plan.version}, native state {_state_label(entry)}"
        )
    print(f"Native listing: {_LIST_COMMAND}")
    print(f"Binary: {binary}")
    print("Start a new Pi session to load the package.")
    if INSTALL_SCOPE_PROJECT in request.scopes:
        print("Project scope may require the user's trust approval before Pi loads it.")


def install_pi_package(request: NativeRequest, binary: str) -> int:
    """Stage Pi's package and retire recognized earlier extension files."""
    template_path = pi_template_path()
    try:
        template = template_path.read_text(encoding="utf-8")
        plan = build_pi_plan(template, binary)
    except OSError as exc:
        print(f"Pi extension template not found at {template_path}: {exc}")
        return 1
    except ValueError as exc:
        print(str(exc))
        return 1
    cutover = PiCutover(request)
    state = _preflight(plan, request, cutover)
    if state is None:
        return 1
    if request.dry_run:
        _print_dry_run(_DryRunContext(plan, request, state, cutover, binary))
        return 0
    run = _InstallRun(_InstallContext(request, plan, cutover, state))
    try:
        run.execute()
    except (
        _InstallFailure,
        NativeCommandError,
        StagingError,
        LegacyRefusal,
        UnsafeInstallPathError,
        OSError,
        ValueError,
    ) as exc:
        print(str(exc))
        incomplete = run.rollback()
        if incomplete:
            print("Incomplete rollback: " + "; ".join(incomplete))
        return 1
    _print_success(plan, request, binary)
    return 0
