"""Auto-update scheduler support for suite-wide installs."""

from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

from slopgate.installer._shared import (
    base_invocation,
    backup_existing_file_and_report,
    find_binary,
    shell_command,
)
from slopgate.installer._suite_autoupdate_types import (
    AUTOUPDATE_MARKER,
    SchedulerPlan,
    WINDOWS_TASK_NAME,
)
from slopgate.installer._suite_autoupdate_windows import (
    prepare_windows_task_replacement,
    scheduler_file_is_owned,
)
from slopgate.util.platform import is_windows, user_config_dir, user_data_dir

DEFAULT_UPDATE_SOURCE = "git+https://github.com/vasceannie/slopgate.git@master"
DEFAULT_UPDATE_INTERVAL_MINUTES = 3 * 10


def _validate_update_source(source: str) -> None:
    if "\n" in source or "\r" in source:
        raise ValueError("update source must not contain newlines")


def _update_suite_args(source: str, *, include_missing: bool) -> list[str]:
    args = [*base_invocation(find_binary()), "update", "--source", source]
    # Scheduled auto-update is package-only by default. Hook rewrites are an
    # explicit interactive maintenance action via `slopgate update --refresh-hooks`.
    if include_missing:
        args.append("--include-missing")
    return args


def _linux_systemd_plan(
    source: str, *, include_missing: bool, interval_minutes: int
) -> SchedulerPlan:
    config_dir = user_config_dir("systemd") / "user"
    service_path = config_dir / "slopgate-auto-update.service"
    timer_path = config_dir / "slopgate-auto-update.timer"
    update_command = shell_command(
        _update_suite_args(source, include_missing=include_missing)
    )
    service = "\n".join(
        [
            f"# {AUTOUPDATE_MARKER}",
            "[Unit]",
            "Description=Update Slopgate package without rewriting harness hooks",
            "Documentation=https://github.com/vasceannie/slopgate",
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
            f"# {AUTOUPDATE_MARKER}",
            "[Unit]",
            "Description=Run Slopgate auto-update while this device is awake",
            "",
            "[Timer]",
            "OnBootSec=5min",
            f"OnUnitActiveSec={interval_minutes}min",
            "RandomizedDelaySec=5min",
            "Persistent=true",
            "Unit=slopgate-auto-update.service",
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
        ["systemctl", "--user", "enable", "--now", "slopgate-auto-update.timer"],
    )


def _macos_launchd_plan(
    source: str, *, include_missing: bool, interval_minutes: int
) -> SchedulerPlan:
    plist_path = (
        Path.home()
        / "Library"
        / "LaunchAgents"
        / "rocks.baked.slopgate.autoupdate.plist"
    )
    interval_seconds = max(60, interval_minutes * 60)
    payload = {
        "Label": "rocks.baked.slopgate.autoupdate",
        "ProgramArguments": _update_suite_args(source, include_missing=include_missing),
        "StartInterval": interval_seconds,
        "RunAtLoad": True,
    }
    raw_content = plistlib.dumps(payload, sort_keys=False).decode("utf-8")
    content = raw_content.replace(
        "<!DOCTYPE plist",
        f"<!-- {AUTOUPDATE_MARKER} -->\n<!DOCTYPE plist",
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
    script_dir = user_data_dir("slopgate")
    script_path = script_dir / "slopgate-auto-update.ps1"
    args = _update_suite_args(source, include_missing=include_missing)
    ps_args = " ".join("'" + arg.replace("'", "''") + "'" for arg in args[1:])
    binary = args[0].replace("'", "''")
    content = "\n".join(
        [
            f"# {AUTOUPDATE_MARKER}",
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
            WINDOWS_TASK_NAME,
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
        if line.startswith("# ") and "slopgate-auto-update." in line
    ]
    if len(header_indexes) != 2:
        raise ValueError(
            "systemd auto-update plan must contain service and timer headers"
        )
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
        return ["systemctl", "--user", "disable", "--now", "slopgate-auto-update.timer"]
    if plan.kind == "launchd":
        return ["launchctl", "unload", "-w", str(plan.target_path)]
    if plan.kind == "windows-schtasks":
        return ["schtasks", "/Delete", "/F", "/TN", WINDOWS_TASK_NAME]
    return None


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

    if prepare_windows_task_replacement(plan) != 0:
        return 1

    for target_path, _content in _scheduler_plan_files(plan):
        if target_path.exists() and not scheduler_file_is_owned(target_path):
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
    existing_paths = [
        target_path for target_path, _content in entries if target_path.exists()
    ]
    print(f"Auto-update scheduler: {plan.kind}")
    if not existing_paths:
        print("No Slopgate auto-update scheduler files found.")
        return 0

    for target_path in existing_paths:
        if not scheduler_file_is_owned(target_path):
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
