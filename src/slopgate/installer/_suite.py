"""Suite-wide install support."""

from __future__ import annotations
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from slopgate.cli.commands import VALID_PLATFORMS
from slopgate.installer.suite import autoupdate
from slopgate.installer.suite import (
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DEFAULT_UPDATE_SOURCE,
    SchedulerPlan,
)
from slopgate.installer.suite import AUTOUPDATE_MARKER
from slopgate.installer._shared import find_binary, shell_command

__all__ = ["AUTOUPDATE_MARKER"]
from slopgate.util.platform import is_windows, user_config_dir, user_data_dir

_INSTALL_TARGETS = VALID_PLATFORMS
CLAUDE_PLATFORM, CODEX_PLATFORM, OPENCODE_PLATFORM, CURSOR_PLATFORM = _INSTALL_TARGETS


@dataclass(frozen=True)
class SuiteInstallOptions:
    """Options for installing hooks across the current device's agent harnesses."""

    dry_run: bool = False
    include_missing: bool = False
    with_autoupdate: bool = True
    source: str = DEFAULT_UPDATE_SOURCE
    interval_minutes: int = DEFAULT_UPDATE_INTERVAL_MINUTES
    install_scope: str = "user"
    project_root: Path | None = None


@dataclass(frozen=True)
class SuiteUninstallOptions:
    """Options for removing hooks across the current device's agent harnesses."""

    dry_run: bool = False
    include_missing: bool = False
    with_autoupdate: bool = True
    install_scope: str = "user"
    project_root: Path | None = None


@dataclass(frozen=True)
class SuiteUpdateOptions:
    """Options for updating Slopgate and optionally refreshing hook install sites."""

    dry_run: bool = False
    source: str = DEFAULT_UPDATE_SOURCE
    include_missing: bool = False
    refresh_hooks: bool = False
    install_scope: str = "user"
    project_root: Path | None = None


@dataclass(frozen=True)
class InstallSite:
    """A platform hook install site on the current device."""

    platform: str
    path: Path
    present: bool


def current_device_label() -> str:
    """Return a concise label for logs without leaking host-specific config."""
    system = platform.system() or sys.platform
    machine = platform.machine() or "unknown-arch"
    return f"{system}/{machine}"


def discover_install_sites(*, include_missing: bool = False) -> list[InstallSite]:
    """Discover current-device hook install sites for supported harnesses."""
    home = Path.home()
    sites = [
        InstallSite(
            CLAUDE_PLATFORM,
            home / ".claude" / "settings.json",
            (home / ".claude").exists(),
        ),
        InstallSite(
            CODEX_PLATFORM, home / ".codex" / "hooks.json", (home / ".codex").exists()
        ),
        InstallSite(
            OPENCODE_PLATFORM,
            user_config_dir(OPENCODE_PLATFORM) / "plugins" / "slopgate-plugin.ts",
            user_config_dir(OPENCODE_PLATFORM).exists(),
        ),
        InstallSite(
            CURSOR_PLATFORM,
            home / ".cursor" / "hooks.json",
            (home / ".cursor").exists(),
        ),
    ]
    if include_missing:
        return sites
    return [site for site in sites if site.present]


def _package_update_command(source: str) -> list[str]:
    uv = shutil.which("uv")
    if uv:
        return [uv, "tool", "install", "--force", source]
    return [sys.executable, "-m", "pip", "install", "--upgrade", source]


def _sync_autoupdate_facade_dependencies() -> None:
    """Keep legacy monkeypatch points on this facade effective for scheduler helpers."""
    autoupdate.find_binary = find_binary
    autoupdate.is_windows = is_windows
    autoupdate.user_config_dir = user_config_dir
    autoupdate.user_data_dir = user_data_dir


def build_scheduler_plan(
    source: str = DEFAULT_UPDATE_SOURCE,
    *,
    include_missing: bool = False,
    interval_minutes: int = DEFAULT_UPDATE_INTERVAL_MINUTES,
) -> SchedulerPlan:
    """Build the native scheduler artifact for the current OS."""
    _sync_autoupdate_facade_dependencies()
    return autoupdate.build_scheduler_plan(
        source, include_missing=include_missing, interval_minutes=interval_minutes
    )


def install_autoupdate(
    *,
    dry_run: bool = False,
    source: str = DEFAULT_UPDATE_SOURCE,
    include_missing: bool = False,
    interval_minutes: int = DEFAULT_UPDATE_INTERVAL_MINUTES,
) -> int:
    """Install the current OS's periodic suite updater."""
    _sync_autoupdate_facade_dependencies()
    return autoupdate.install_autoupdate(
        dry_run=dry_run,
        source=source,
        include_missing=include_missing,
        interval_minutes=interval_minutes,
    )


def uninstall_autoupdate(*, dry_run: bool = False) -> int:
    """Remove the current OS's periodic suite updater without touching unknown files."""
    _sync_autoupdate_facade_dependencies()
    return autoupdate.uninstall_autoupdate(dry_run=dry_run)


def install_suite(options: SuiteInstallOptions | None = None) -> int:
    """Install Slopgate hooks for all detected harnesses on this device."""
    from slopgate.installer import install_platform

    resolved_options = options or SuiteInstallOptions()
    sites = discover_install_sites(include_missing=resolved_options.include_missing)
    print(f"Device: {current_device_label()}")
    if not sites:
        print(
            "No existing agent harness install sites detected; use --include-missing to create all supported sites."
        )
    status = 0
    for site in sites:
        print(f"Installing {site.platform} hooks at {site.path}")
        if resolved_options.dry_run:
            print(f"Would install: {site.platform}")
            continue
        status = (
            install_platform(
                site.platform,
                dry_run=False,
                install_scope=resolved_options.install_scope,
                project_root=resolved_options.project_root,
            )
            or status
        )
    if resolved_options.with_autoupdate and status == 0:
        status = (
            install_autoupdate(
                dry_run=resolved_options.dry_run,
                source=resolved_options.source,
                include_missing=resolved_options.include_missing,
                interval_minutes=resolved_options.interval_minutes,
            )
            or status
        )
    return status


def uninstall_suite(options: SuiteUninstallOptions | None = None) -> int:
    """Remove Slopgate hooks for all detected harnesses on this device."""
    from slopgate.installer import uninstall_platform

    resolved_options = options or SuiteUninstallOptions()
    sites = discover_install_sites(include_missing=resolved_options.include_missing)
    print(f"Device: {current_device_label()}")
    status = 0
    for site in sites:
        print(f"Uninstalling {site.platform} hooks at {site.path}")
        if resolved_options.dry_run:
            print(f"Would uninstall: {site.platform}")
            continue
        status = (
            uninstall_platform(
                site.platform,
                dry_run=False,
                install_scope=resolved_options.install_scope,
                project_root=resolved_options.project_root,
            )
            or status
        )
    if resolved_options.with_autoupdate:
        status = uninstall_autoupdate(dry_run=resolved_options.dry_run) or status
    return status


def update_suite(options: SuiteUpdateOptions) -> int:
    """Update Slopgate from GitHub and optionally refresh local hook sites."""
    from slopgate.installer import install_platform

    print(f"Device: {current_device_label()}")
    update_command = _package_update_command(options.source)
    print("Update source: " + options.source)
    if options.dry_run:
        print("Would run: " + shell_command(update_command))
    else:
        env = os.environ.copy()
        env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
        completed = subprocess.run(update_command, check=False, env=env)
        if completed.returncode != 0:
            return completed.returncode
    if not options.refresh_hooks:
        print("Hook refresh: skipped (use --refresh-hooks to rewrite harness hooks)")
        return 0
    status = 0
    for site in discover_install_sites(include_missing=options.include_missing):
        print(f"Refreshing {site.platform} hooks at {site.path}")
        if options.dry_run:
            print(f"Would install: {site.platform}")
            continue
        status = (
            install_platform(
                site.platform,
                dry_run=False,
                install_scope=options.install_scope,
                project_root=options.project_root,
            )
            or status
        )
    return status
