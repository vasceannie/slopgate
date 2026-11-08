from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import slopgate.installer._suite
from slopgate.cli.commands import cmd_install_suite, cmd_uninstall, cmd_update_suite
from slopgate.cli.parsers import build_parser
from slopgate.installer.suite import autoupdate
from tests.native.hosts import FakeHosts, tree_digest
from tests.support import SKIP_DARWIN_ONLY, SKIP_LINUX_ONLY, SKIP_WINDOWS_ONLY

WINDOWS_SLOPGATE_EXE = "C:\\Tools\\slopgate.exe"


def patch_linux_installer_config_dirs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    config_home = tmp_path / ".config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    def fake_user_config_dir(app_name: str) -> Path:
        return config_home / app_name

    monkeypatch.setattr(slopgate.installer._suite, "is_windows", lambda: False)
    monkeypatch.setattr(slopgate.installer._suite.sys, "platform", "linux")
    monkeypatch.setattr(autoupdate, "is_windows", lambda: False)
    monkeypatch.setattr(autoupdate.sys, "platform", "linux")
    monkeypatch.setattr(
        slopgate.installer._suite, "user_config_dir", fake_user_config_dir
    )
    monkeypatch.setattr(autoupdate, "user_config_dir", fake_user_config_dir)
    return config_home


def record_suite_subprocess_run(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    run_commands: list[list[str]] = []

    def fake_run(
        command: list[str], _check: bool = False, **_kwargs: object
    ) -> subprocess.CompletedProcess[list[str]]:
        run_commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(slopgate.installer._suite.subprocess, "run", fake_run)
    return run_commands


def test_install_suite_parser_exposes_device_aware_autoupdate_flags() -> None:
    args = build_parser().parse_args(
        ["setup", "--dry-run", "--include-missing", "--interval-minutes", "45"]
    )
    assert (
        args.command,
        args.dry_run,
        args.with_autoupdate,
        args.include_missing,
        args.interval_minutes,
    ) == ("setup", True, True, True, 45)


def test_install_suite_parser_keeps_platform_choices_out_of_hook_platforms() -> None:
    args = build_parser().parse_args(["setup", "--dry-run"])
    assert (args.command, args.func, args.dry_run, args.with_autoupdate) == (
        "setup",
        cmd_install_suite,
        True,
        True,
    )


def test_native_install_all_parser_supports_autoupdate() -> None:
    args = build_parser().parse_args(["install", "all", "--dry-run"])
    assert (args.command, args.platform, args.with_autoupdate, args.dry_run) == (
        "install",
        "all",
        True,
        True,
    )


def test_native_uninstall_all_parser_supports_autoupdate() -> None:
    args = build_parser().parse_args(["uninstall", "all", "--dry-run"])
    assert (
        args.command,
        args.func,
        args.platform,
        args.with_autoupdate,
        args.dry_run,
    ) == ("uninstall", cmd_uninstall, "all", True, True)


def test_native_install_parser_supports_pi() -> None:
    args = build_parser().parse_args(["install", "pi", "--dry-run"])
    assert (
        args.command,
        args.platform,
        args.with_autoupdate,
        args.dry_run,
    ) == ("install", "pi", True, True)


def test_native_install_parser_supports_omp() -> None:
    args = build_parser().parse_args(["install", "omp", "--dry-run"])
    assert (
        args.command,
        args.platform,
        args.with_autoupdate,
        args.dry_run,
    ) == ("install", "omp", True, True)


def test_update_suite_parser_keeps_platform_choices_out_of_hook_platforms() -> None:
    args = build_parser().parse_args(["update", "--dry-run"])
    assert (
        args.command,
        args.func,
        args.dry_run,
        args.source,
        hasattr(args, "platform"),
    ) == (
        "update",
        cmd_update_suite,
        True,
        "git+https://github.com/vasceannie/slopgate.git@master",
        False,
    )


@SKIP_LINUX_ONLY
def test_linux_scheduler_plan_uses_systemd_user_timer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config_home = patch_linux_installer_config_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(
        slopgate.installer._suite, "find_binary", lambda: "/tmp/slopgate bin"
    )
    plan = slopgate.installer._suite.build_scheduler_plan(
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
        config_home / "systemd/user/slopgate-auto-update.timer",
        True,
        True,
        True,
    )


@SKIP_DARWIN_ONLY
def test_macos_scheduler_plan_uses_launch_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(slopgate.installer._suite, "is_windows", lambda: False)
    monkeypatch.setattr(slopgate.installer._suite.sys, "platform", "darwin")
    monkeypatch.setattr(
        slopgate.installer._suite, "find_binary", lambda: "/usr/local/bin/slopgate"
    )
    plan = slopgate.installer._suite.build_scheduler_plan(interval_minutes=20)
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


@SKIP_WINDOWS_ONLY
def test_windows_scheduler_plan_records_removed_autoupdater(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setattr(slopgate.installer._suite, "is_windows", lambda: True)
    monkeypatch.setattr(
        slopgate.installer._suite, "find_binary", lambda: WINDOWS_SLOPGATE_EXE
    )
    plan = slopgate.installer._suite.build_scheduler_plan(interval_minutes=11)
    assert (
        plan.kind,
        plan.target_path,
        plan.enable_command,
        "Windows auto-updater removed" in plan.content,
        "slopgate update" in plan.content,
    ) == (
        "windows-schtasks",
        tmp_path / ".slopgate" / "auto-update.task",
        None,
        True,
        True,
    )


@SKIP_LINUX_ONLY
def test_scheduler_plan_falls_back_to_python_module_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    patch_linux_installer_config_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(
        slopgate.installer._suite, "find_binary", lambda: sys.executable
    )
    plan = slopgate.installer._suite.build_scheduler_plan()
    exec_start = next(
        (line for line in plan.content.splitlines() if line.startswith("ExecStart="))
    )
    assert "-m" in exec_start and "slopgate" in exec_start and "update" in exec_start


@SKIP_LINUX_ONLY
def test_default_scheduler_plan_tracks_canonical_master_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    patch_linux_installer_config_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(
        slopgate.installer._suite,
        "find_binary",
        lambda: "/home/trav/.local/bin/slopgate",
    )
    plan = slopgate.installer._suite.build_scheduler_plan()
    assert "git+https://github.com/vasceannie/slopgate.git@master" in plan.content
    assert "git+https://github.com/vasceannie/slopgate.git@main" not in plan.content


@SKIP_LINUX_ONLY
def test_scheduler_plan_rejects_newline_source_for_systemd_units(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setattr(slopgate.installer._suite, "is_windows", lambda: False)
    monkeypatch.setattr(slopgate.installer._suite.sys, "platform", "linux")
    with pytest.raises(ValueError, match="source"):
        slopgate.installer._suite.build_scheduler_plan(
            "git+https://example.invalid/vf.git@main\nExecStart=/bin/sh"
        )


def linux_autoupdate_units(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config_home = patch_linux_installer_config_dirs(monkeypatch, tmp_path)
    service = config_home / "systemd/user/slopgate-auto-update.service"
    timer = config_home / "systemd/user/slopgate-auto-update.timer"
    service.parent.mkdir(parents=True)
    return (service, timer)


def macos_autoupdate_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(slopgate.installer._suite, "is_windows", lambda: False)
    monkeypatch.setattr(slopgate.installer._suite.sys, "platform", "darwin")
    monkeypatch.setattr(autoupdate, "is_windows", lambda: False)
    monkeypatch.setattr(autoupdate.sys, "platform", "darwin")
    monkeypatch.setattr(
        slopgate.installer._suite, "find_binary", lambda: "/usr/local/bin/slopgate"
    )


def test_install_suite_dry_run_installs_detected_sites_without_writing(
    native_hosts: FakeHosts, capsys: pytest.CaptureFixture[str]
) -> None:
    (native_hosts.home / ".codex").mkdir()
    before = tree_digest(native_hosts.home)
    status = slopgate.installer.install_suite(
        slopgate.installer.SuiteInstallOptions(dry_run=True)
    )
    output = capsys.readouterr().out
    assert status == 0, "suite dry-run should report a successful preview"
    assert (
        "Installing codex (native hooks (not a registered plugin); user scope)"
        in output
    )
    assert "Installing claude (native plugin; user scope)" in output
    assert tree_digest(native_hosts.home) == before, (
        "suite dry-run must not alter host settings or native staging"
    )
    assert native_hosts.mutating_calls() == [], (
        "suite dry-run must not invoke mutating native manager commands"
    )


def test_uninstall_suite_dry_run_reports_detected_sites_without_writing(
    native_hosts: FakeHosts, capsys: pytest.CaptureFixture[str]
) -> None:
    (native_hosts.home / ".claude").mkdir()
    before = tree_digest(native_hosts.home)
    status = slopgate.installer.uninstall_suite(
        slopgate.installer.SuiteUninstallOptions(dry_run=True)
    )
    output = capsys.readouterr().out
    assert status == 0, "suite uninstall dry-run should report a successful preview"
    assert "Uninstalling claude (native plugin; user scope)" in output
    assert tree_digest(native_hosts.home) == before, (
        "suite uninstall dry-run must not alter host settings or native staging"
    )
    assert native_hosts.mutating_calls() == [], (
        "suite uninstall dry-run must not invoke mutating native manager commands"
    )
