from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import slopgate.installer._suite as suite
from slopgate.cli.commands import cmd_install_suite, cmd_uninstall, cmd_update_suite
from slopgate.cli.parsers import build_parser


def _record_suite_subprocess_run(monkeypatch: Any) -> list[list[str]]:
    run_commands: list[list[str]] = []

    def fake_run(command: list[str], check: bool = False) -> subprocess.CompletedProcess[list[str]]:
        run_commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(suite.subprocess, "run", fake_run)
    return run_commands


def test_install_suite_parser_exposes_device_aware_autoupdate_flags() -> None:
    args = build_parser().parse_args(
        [
            "install-suite",
            "--dry-run",
            "--with-autoupdate",
            "--include-missing",
            "--interval-minutes",
            "45",
        ]
    )

    assert (
        args.command,
        args.dry_run,
        args.with_autoupdate,
        args.include_missing,
        args.interval_minutes,
    ) == ("install-suite", True, True, True, 45)


def test_install_suite_parser_keeps_platform_choices_out_of_hook_platforms() -> None:
    args = build_parser().parse_args(["install-suite", "--with-autoupdate", "--dry-run"])

    assert (args.command, args.func, args.dry_run, args.with_autoupdate) == (
        "install-suite",
        cmd_install_suite,
        True,
        True,
    )


def test_native_install_all_parser_supports_autoupdate() -> None:
    args = build_parser().parse_args(
        ["install", "all", "--with-autoupdate", "--dry-run"]
    )

    assert (args.command, args.platform, args.with_autoupdate, args.dry_run) == (
        "install",
        "all",
        True,
        True,
    )


def test_native_uninstall_all_parser_supports_autoupdate() -> None:
    args = build_parser().parse_args(
        ["uninstall", "all", "--with-autoupdate", "--dry-run"]
    )

    assert (args.command, args.func, args.platform, args.with_autoupdate, args.dry_run) == (
        "uninstall",
        cmd_uninstall,
        "all",
        True,
        True,
    )


def test_update_suite_parser_keeps_platform_choices_out_of_hook_platforms() -> None:
    args = build_parser().parse_args(["update-suite", "--dry-run"])

    assert (args.command, args.func, args.dry_run, hasattr(args, "platform")) == (
        "update-suite",
        cmd_update_suite,
        True,
        False,
    )


def test_discover_install_sites_respects_current_device_home(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".config" / "opencode").mkdir(parents=True)

    sites = suite.discover_install_sites()

    assert (
        [(site.platform, site.present) for site in sites],
        [site.platform for site in suite.discover_install_sites(include_missing=True)],
    ) == (
        [("claude", True), ("opencode", True)],
        ["claude", "codex", "opencode", "cursor"],
    )


def test_linux_scheduler_plan_uses_systemd_user_timer(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setattr(suite, "is_windows", lambda: False)
    monkeypatch.setattr(suite.sys, "platform", "linux")
    monkeypatch.setattr(suite, "find_binary", lambda: "/tmp/slopgate bin")

    plan = suite.build_scheduler_plan(
        "git+https://github.com/example/slopgate.git@master",
        include_missing=True,
        interval_minutes=17,
    )

    assert (
        plan.kind,
        plan.target_path,
        "OnUnitActiveSec=17min" in plan.content,
        "--include-missing" in plan.content,
        "slopgate-auto-update.timer" in (plan.enable_command or []),
    ) == (
        "systemd-user",
        tmp_path / ".config/systemd/user/slopgate-auto-update.timer",
        True,
        True,
        True,
    )


def test_macos_scheduler_plan_uses_launch_agent(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(suite, "is_windows", lambda: False)
    monkeypatch.setattr(suite.sys, "platform", "darwin")
    monkeypatch.setattr(suite, "find_binary", lambda: "/usr/local/bin/slopgate")

    plan = suite.build_scheduler_plan(interval_minutes=20)

    assert (
        plan.kind,
        plan.target_path,
        "<integer>1200</integer>" in plan.content,
        plan.enable_command,
    ) == (
        "launchd",
        tmp_path / "Library/LaunchAgents/rocks.baked.slopgate.autoupdate.plist",
        True,
        ["launchctl", "load", "-w", str(plan.target_path)],
    )


def test_windows_scheduler_plan_uses_schtasks(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setattr(suite, "is_windows", lambda: True)

    def fake_user_data_dir(app_name: str) -> Path:
        return tmp_path / "LocalAppData" / app_name

    monkeypatch.setattr(suite, "user_data_dir", fake_user_data_dir)
    monkeypatch.setattr(suite, "find_binary", lambda: "C:\\Tools\\slopgate.exe")

    plan = suite.build_scheduler_plan(interval_minutes=11)

    assert (
        plan.kind,
        plan.target_path,
        "C:\\Tools\\slopgate.exe" in plan.content,
        "/MO" in (plan.enable_command or []),
        "11" in (plan.enable_command or []),
    ) == (
        "windows-schtasks",
        tmp_path / "LocalAppData/slopgate/slopgate-auto-update.ps1",
        True,
        True,
        True,
    )


def test_scheduler_plan_falls_back_to_python_module_invocation(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setattr(suite, "is_windows", lambda: False)
    monkeypatch.setattr(suite.sys, "platform", "linux")
    monkeypatch.setattr(suite, "find_binary", lambda: sys.executable)

    plan = suite.build_scheduler_plan()

    exec_start = next(line for line in plan.content.splitlines() if line.startswith("ExecStart="))
    assert " -m slopgate update-suite " in exec_start


def test_scheduler_plan_rejects_newline_source_for_systemd_units(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setattr(suite, "is_windows", lambda: False)
    monkeypatch.setattr(suite.sys, "platform", "linux")

    try:
        suite.build_scheduler_plan("git+https://example.invalid/vf.git@main\nExecStart=/bin/sh")
    except ValueError as exc:
        assert "source" in str(exc)
    else:
        raise AssertionError("newline source should be rejected before rendering")


def test_macos_scheduler_plan_escapes_plist_arguments(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(suite, "is_windows", lambda: False)
    monkeypatch.setattr(suite.sys, "platform", "darwin")
    monkeypatch.setattr(suite, "find_binary", lambda: "/usr/local/bin/slopgate")

    plan = suite.build_scheduler_plan("git+https://example.invalid/vf.git?x=1&y=<two>")

    parsed = plistlib.loads(plan.content.encode("utf-8"))
    assert parsed["ProgramArguments"][-1] == "git+https://example.invalid/vf.git?x=1&y=<two>"


