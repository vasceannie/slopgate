"""Suite-wide install and auto-update support."""

from __future__ import annotations

import os
import platform
import plistlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from vibeforcer.cli.commands import VALID_PLATFORMS
from vibeforcer.installer._shared import (
    base_invocation,
    backup_existing_file_and_report,
    find_binary,
    shell_command,
)
from vibeforcer.util.platform import is_windows, user_config_dir, user_data_dir

DEFAULT_UPDATE_SOURCE = "git+https://github.com/vasceannie/vibeforcer.git@master"
DEFAULT_UPDATE_INTERVAL_MINUTES = 3 * 10
_AUTOUPDATE_MARKER = "Vibeforcer auto-update managed file"
_INSTALL_TARGETS = VALID_PLATFORMS
CLAUDE_PLATFORM, CODEX_PLATFORM, OPENCODE_PLATFORM = _INSTALL_TARGETS


@dataclass(frozen=True)
class SuiteInstallOptions:
    """Options for installing hooks across the current device's agent harnesses."""

    dry_run: bool = False
    include_missing: bool = False
    with_autoupdate: bool = False
    source: str = DEFAULT_UPDATE_SOURCE
    interval_minutes: int = DEFAULT_UPDATE_INTERVAL_MINUTES


@dataclass(frozen=True)
class SuiteUninstallOptions:
    """Options for removing hooks across the current device's agent harnesses."""

    dry_run: bool = False
    include_missing: bool = False
    with_autoupdate: bool = False


@dataclass(frozen=True)
class InstallSite:
    """A platform hook install site on the current device."""

    platform: str
    path: Path
    present: bool


@dataclass(frozen=True)
class SchedulerPlan:
    """OS-specific auto-update scheduler plan."""

    kind: str
    target_path: Path
    content: str
    enable_command: list[str] | None


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
            CODEX_PLATFORM,
            home / ".codex" / "hooks.json",
            (home / ".codex").exists(),
        ),
        InstallSite(
            OPENCODE_PLATFORM,
            user_config_dir(OPENCODE_PLATFORM) / "plugins" / "vibeforcer-plugin.ts",
            user_config_dir(OPENCODE_PLATFORM).exists(),
        ),
    ]
    if include_missing:
        return sites
    return [site for site in sites if site.present]


def _package_update_command(source: str) -> list[str]:
    pipx = shutil.which("pipx")
    if pipx:
        return [pipx, "install", "--force", source]
    uv = shutil.which("uv")
    if uv:
        return [uv, "tool", "install", "--force", source]
    return [sys.executable, "-m", "pip", "install", "--upgrade", source]


def _validate_update_source(source: str) -> None:
    if "\n" in source or "\r" in source:
        raise ValueError("update source must not contain newlines")


def _update_suite_args(source: str, *, include_missing: bool) -> list[str]:
    args = [*base_invocation(find_binary()), "update-suite", "--source", source]
    if include_missing:
        args.append("--include-missing")
    return args


def _linux_systemd_plan(
    source: str, *, include_missing: bool, interval_minutes: int
) -> SchedulerPlan:
    config_dir = user_config_dir("systemd") / "user"
    service_path = config_dir / "vibeforcer-auto-update.service"
    timer_path = config_dir / "vibeforcer-auto-update.timer"
    update_command = shell_command(_update_suite_args(source, include_missing=include_missing))
    service = "\n".join(
        [
            f"# {_AUTOUPDATE_MARKER}",
            "[Unit]",
            "Description=Update Vibeforcer from GitHub and refresh local hook install sites",
            "Documentation=https://github.com/vasceannie/vibeforcer",
            "",
            "[Service]",
            "Type=oneshot",
            f"Environment=HOME={Path.home()}",
            f"ExecStart={update_command}",
            "",
        ]
    )
    timer = "\n".join(
        [
            f"# {_AUTOUPDATE_MARKER}",
            "[Unit]",
            "Description=Run Vibeforcer auto-update while this device is awake",
            "",
            "[Timer]",
            "OnBootSec=5min",
            f"OnUnitActiveSec={interval_minutes}min",
            "RandomizedDelaySec=5min",
            "Persistent=true",
            "Unit=vibeforcer-auto-update.service",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]
    )
    return SchedulerPlan(
        "systemd-user",
        timer_path,
        f"# {service_path}\n{service}\n# {timer_path}\n{timer}",
        ["systemctl", "--user", "enable", "--now", "vibeforcer-auto-update.timer"],
    )


def _macos_launchd_plan(
    source: str, *, include_missing: bool, interval_minutes: int
) -> SchedulerPlan:
    plist_path = (
        Path.home() / "Library" / "LaunchAgents" / "rocks.baked.vibeforcer.autoupdate.plist"
    )
    interval_seconds = max(60, interval_minutes * 60)
    payload = {
        "Label": "rocks.baked.vibeforcer.autoupdate",
        "ProgramArguments": _update_suite_args(source, include_missing=include_missing),
        "StartInterval": interval_seconds,
        "RunAtLoad": True,
    }
    raw_content = plistlib.dumps(payload, sort_keys=False).decode("utf-8")
    content = raw_content.replace(
        "<!DOCTYPE plist",
        f"<!-- {_AUTOUPDATE_MARKER} -->\n<!DOCTYPE plist",
        1,
    )
    return SchedulerPlan(
        "launchd",
        plist_path,
        content,
        ["launchctl", "load", "-w", str(plist_path)],
    )


def _windows_task_plan(
    source: str, *, include_missing: bool, interval_minutes: int
) -> SchedulerPlan:
    script_dir = user_data_dir("vibeforcer")
    script_path = script_dir / "vibeforcer-auto-update.ps1"
    args = _update_suite_args(source, include_missing=include_missing)
    ps_args = " ".join("'" + arg.replace("'", "''") + "'" for arg in args[1:])
    binary = args[0].replace("'", "''")
    content = "\n".join(
        [
            f"# {_AUTOUPDATE_MARKER}",
            "$ErrorActionPreference = 'Stop'",
            f"& '{binary}' {ps_args}",
            "",
        ]
    )
    task_command = (
        "PowerShell -NoProfile -ExecutionPolicy Bypass -File "
        + subprocess.list2cmdline([str(script_path)])
    )
    return SchedulerPlan(
        "windows-schtasks",
        script_path,
        content,
        [
            "schtasks",
            "/Create",
            "/F",
            "/SC",
            "MINUTE",
            "/MO",
            str(max(1, interval_minutes)),
            "/TN",
            "Vibeforcer Auto Update",
            "/TR",
            task_command,
        ],
    )


def build_scheduler_plan(
    source: str = DEFAULT_UPDATE_SOURCE,
    *,
    include_missing: bool = False,
    interval_minutes: int = DEFAULT_UPDATE_INTERVAL_MINUTES,
) -> SchedulerPlan:
    """Build the native scheduler artifact for the current OS."""

    _validate_update_source(source)

    if is_windows():
        return _windows_task_plan(
            source, include_missing=include_missing, interval_minutes=interval_minutes
        )
    if sys.platform == "darwin":
        return _macos_launchd_plan(
            source, include_missing=include_missing, interval_minutes=interval_minutes
        )
    return _linux_systemd_plan(
        source, include_missing=include_missing, interval_minutes=interval_minutes
    )


def _systemd_plan_files(plan: SchedulerPlan) -> list[tuple[Path, str]]:
    lines = plan.content.splitlines()
    header_indexes = [
        index
        for index, line in enumerate(lines)
        if line.startswith("# ") and "vibeforcer-auto-update." in line
    ]
    if len(header_indexes) != 2:
        raise ValueError("systemd auto-update plan must contain service and timer headers")
    service_index, timer_index = header_indexes
    service_path = Path(lines[service_index].removeprefix("# "))
    timer_path = Path(lines[timer_index].removeprefix("# "))
    service_body = "\n".join(lines[service_index + 1 : timer_index]) + "\n"
    timer_body = "\n".join(lines[timer_index + 1 :]) + "\n"
    return [(service_path, service_body), (timer_path, timer_body)]


def _scheduler_plan_files(plan: SchedulerPlan) -> list[tuple[Path, str]]:
    if plan.kind == "systemd-user":
        return _systemd_plan_files(plan)
    return [(plan.target_path, plan.content)]


def _scheduler_disable_command(plan: SchedulerPlan) -> list[str] | None:
    if plan.kind == "systemd-user":
        return ["systemctl", "--user", "disable", "--now", "vibeforcer-auto-update.timer"]
    if plan.kind == "launchd":
        return ["launchctl", "unload", "-w", str(plan.target_path)]
    if plan.kind == "windows-schtasks":
        return ["schtasks", "/Delete", "/F", "/TN", "Vibeforcer Auto Update"]
    return None


def _scheduler_file_is_owned(path: Path) -> bool:
    content = path.read_text(encoding="utf-8", errors="replace")
    marker_line = f"# {_AUTOUPDATE_MARKER}"
    plist_marker = f"<!-- {_AUTOUPDATE_MARKER} -->"
    return any(line.strip() in {marker_line, plist_marker} for line in content.splitlines()[:3])


def install_autoupdate(
    *,
    dry_run: bool = False,
    source: str = DEFAULT_UPDATE_SOURCE,
    include_missing: bool = False,
    interval_minutes: int = DEFAULT_UPDATE_INTERVAL_MINUTES,
) -> int:
    """Install the current OS's periodic suite updater."""

    plan = build_scheduler_plan(
        source,
        include_missing=include_missing,
        interval_minutes=interval_minutes,
    )
    print(f"Auto-update scheduler: {plan.kind}")
    print(f"Target: {plan.target_path}")
    if dry_run:
        print(plan.content)
        if plan.enable_command:
            print("Would run: " + shell_command(plan.enable_command))
        return 0

    for target_path, _content in _scheduler_plan_files(plan):
        if target_path.exists() and not _scheduler_file_is_owned(target_path):
            print(f"Refusing to overwrite unrecognized auto-update file: {target_path}")
            return 1

    for target_path, content in _scheduler_plan_files(plan):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        backup_existing_file_and_report(target_path, "auto-update file")
        target_path.write_text(content, encoding="utf-8")
    if plan.enable_command is None:
        return 0
    completed = subprocess.run(plan.enable_command, check=False)
    return completed.returncode


def uninstall_autoupdate(*, dry_run: bool = False) -> int:
    """Remove the current OS's periodic suite updater without touching unknown files."""

    plan = build_scheduler_plan()
    entries = _scheduler_plan_files(plan)
    existing_paths = [target_path for target_path, _content in entries if target_path.exists()]
    print(f"Auto-update scheduler: {plan.kind}")
    if not existing_paths:
        print("No Vibeforcer auto-update scheduler files found.")
        return 0

    for target_path in existing_paths:
        if not _scheduler_file_is_owned(target_path):
            print(f"Refusing to remove unrecognized auto-update file: {target_path}")
            return 1

    disable_command = _scheduler_disable_command(plan)
    if dry_run:
        for target_path in existing_paths:
            print(f"Would back up and delete: {target_path}")
        if disable_command:
            print("Would run: " + shell_command(disable_command))
        return 0

    if disable_command:
        completed = subprocess.run(disable_command, check=False)
        if completed.returncode != 0:
            return completed.returncode
    for target_path in existing_paths:
        backup_existing_file_and_report(target_path, "auto-update file")
        target_path.unlink()
        print(f"Removed: {target_path}")
    return 0


def install_suite(options: SuiteInstallOptions | None = None) -> int:
    """Install Vibeforcer hooks for all detected harnesses on this device."""

    from vibeforcer.installer import install_platform

    resolved_options = options or SuiteInstallOptions()
    sites = discover_install_sites(include_missing=resolved_options.include_missing)
    print(f"Device: {current_device_label()}")
    if not sites:
        print(
            "No existing agent harness install sites detected; "
            "use --include-missing to create all supported sites."
        )
    status = 0
    for site in sites:
        print(f"Installing {site.platform} hooks at {site.path}")
        if resolved_options.dry_run:
            print(f"Would install: {site.platform}")
            continue
        status = install_platform(site.platform, dry_run=False) or status
    if resolved_options.with_autoupdate and status == 0:
        status = install_autoupdate(
            dry_run=resolved_options.dry_run,
            source=resolved_options.source,
            include_missing=resolved_options.include_missing,
            interval_minutes=resolved_options.interval_minutes,
        ) or status
    return status


def uninstall_suite(options: SuiteUninstallOptions | None = None) -> int:
    """Remove Vibeforcer hooks for all detected harnesses on this device."""

    from vibeforcer.installer import uninstall_platform

    resolved_options = options or SuiteUninstallOptions()
    sites = discover_install_sites(include_missing=resolved_options.include_missing)
    print(f"Device: {current_device_label()}")
    status = 0
    for site in sites:
        print(f"Uninstalling {site.platform} hooks at {site.path}")
        if resolved_options.dry_run:
            print(f"Would uninstall: {site.platform}")
            continue
        status = uninstall_platform(site.platform, dry_run=False) or status
    if resolved_options.with_autoupdate:
        status = uninstall_autoupdate(dry_run=resolved_options.dry_run) or status
    return status


def update_suite(
    *,
    dry_run: bool = False,
    source: str = DEFAULT_UPDATE_SOURCE,
    include_missing: bool = False,
) -> int:
    """Update Vibeforcer from GitHub, then refresh detected local hook sites."""

    from vibeforcer.installer import install_platform

    print(f"Device: {current_device_label()}")
    update_command = _package_update_command(source)
    print("Update source: " + source)
    if dry_run:
        print("Would run: " + shell_command(update_command))
    else:
        env = os.environ.copy()
        env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
        completed = subprocess.run(update_command, check=False, env=env)
        if completed.returncode != 0:
            return completed.returncode

    status = 0
    for site in discover_install_sites(include_missing=include_missing):
        print(f"Refreshing {site.platform} hooks at {site.path}")
        if dry_run:
            print(f"Would install: {site.platform}")
            continue
        status = install_platform(site.platform, dry_run=False) or status
    return status
