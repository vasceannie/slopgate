from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import vibeforcer.installer as installer_module
import vibeforcer.installer._suite as suite
from vibeforcer.cli.commands import cmd_install, cmd_install_suite, cmd_uninstall, cmd_update_suite
from vibeforcer.cli.parsers import build_parser


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

    assert args.command == "install"
    assert args.platform == "all"
    assert args.with_autoupdate is True
    assert args.dry_run is True


def test_native_uninstall_all_parser_supports_autoupdate() -> None:
    args = build_parser().parse_args(
        ["uninstall", "all", "--with-autoupdate", "--dry-run"]
    )

    assert args.command == "uninstall"
    assert args.func == cmd_uninstall
    assert args.platform == "all"
    assert args.with_autoupdate is True
    assert args.dry_run is True


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
        ["claude", "codex", "opencode"],
    )


def test_linux_scheduler_plan_uses_systemd_user_timer(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setattr(suite, "is_windows", lambda: False)
    monkeypatch.setattr(suite.sys, "platform", "linux")
    monkeypatch.setattr(suite, "find_binary", lambda: "/tmp/vibeforcer bin")

    plan = suite.build_scheduler_plan(
        "git+https://github.com/example/vibeforcer.git@master",
        include_missing=True,
        interval_minutes=17,
    )

    assert (
        plan.kind,
        plan.target_path,
        "OnUnitActiveSec=17min" in plan.content,
        "--include-missing" in plan.content,
        "vibeforcer-auto-update.timer" in (plan.enable_command or []),
    ) == (
        "systemd-user",
        tmp_path / ".config/systemd/user/vibeforcer-auto-update.timer",
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
    monkeypatch.setattr(suite, "find_binary", lambda: "/usr/local/bin/vibeforcer")

    plan = suite.build_scheduler_plan(interval_minutes=20)

    assert (
        plan.kind,
        plan.target_path,
        "<integer>1200</integer>" in plan.content,
        plan.enable_command,
    ) == (
        "launchd",
        tmp_path / "Library/LaunchAgents/rocks.baked.vibeforcer.autoupdate.plist",
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
    monkeypatch.setattr(suite, "find_binary", lambda: "C:\\Tools\\vibeforcer.exe")

    plan = suite.build_scheduler_plan(interval_minutes=11)

    assert (
        plan.kind,
        plan.target_path,
        "C:\\Tools\\vibeforcer.exe" in plan.content,
        "/MO" in (plan.enable_command or []),
        "11" in (plan.enable_command or []),
    ) == (
        "windows-schtasks",
        tmp_path / "LocalAppData/vibeforcer/vibeforcer-auto-update.ps1",
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
    assert " -m vibeforcer update-suite " in exec_start


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
    monkeypatch.setattr(suite, "find_binary", lambda: "/usr/local/bin/vibeforcer")

    plan = suite.build_scheduler_plan("git+https://example.invalid/vf.git?x=1&y=<two>")

    parsed = plistlib.loads(plan.content.encode("utf-8"))
    assert parsed["ProgramArguments"][-1] == "git+https://example.invalid/vf.git?x=1&y=<two>"


def test_linux_autoupdate_install_refuses_unowned_existing_units(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setattr(suite, "is_windows", lambda: False)
    monkeypatch.setattr(suite.sys, "platform", "linux")
    service = tmp_path / ".config/systemd/user/vibeforcer-auto-update.service"
    timer = tmp_path / ".config/systemd/user/vibeforcer-auto-update.timer"
    service.parent.mkdir(parents=True)
    service.write_text("custom service\n", encoding="utf-8")
    timer.write_text("custom timer\n", encoding="utf-8")

    assert suite.install_autoupdate(dry_run=False) == 1

    assert service.read_text(encoding="utf-8") == "custom service\n"
    assert timer.read_text(encoding="utf-8") == "custom timer\n"
    assert not sorted(service.parent.glob("*.vibeforcer-bak-*"))


def test_autoupdate_uninstall_refuses_incidental_scheduler_marker_text(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setattr(suite, "is_windows", lambda: False)
    monkeypatch.setattr(suite.sys, "platform", "linux")
    timer = tmp_path / ".config/systemd/user/vibeforcer-auto-update.timer"
    timer.parent.mkdir(parents=True)
    timer.write_text("# custom comment mentions vibeforcer-auto-update\n[Timer]\n", encoding="utf-8")

    assert suite.uninstall_autoupdate(dry_run=False) == 1

    assert timer.exists()
    assert not sorted(timer.parent.glob("*.vibeforcer-bak-*"))


def test_install_with_autoupdate_stops_when_platform_install_fails(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    calls: list[bool] = []

    def fail_install(_platform: str, dry_run: bool = False) -> int:
        return 1

    def fake_autoupdate(**_kwargs: object) -> int:
        calls.append(True)
        return 0

    monkeypatch.setattr(installer_module, "install_platform", fail_install)
    monkeypatch.setattr(suite, "install_autoupdate", fake_autoupdate)

    args = build_parser().parse_args(["install", "claude", "--with-autoupdate"])
    assert args.func is cmd_install
    assert cmd_install(args) == 1
    assert calls == []


def test_install_suite_with_autoupdate_stops_when_platform_install_fails(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".claude").mkdir()
    calls: list[bool] = []

    def fail_install(_platform: str, dry_run: bool = False) -> int:
        return 1

    def fake_autoupdate(**_kwargs: object) -> int:
        calls.append(True)
        return 0

    monkeypatch.setattr(installer_module, "install_platform", fail_install)
    monkeypatch.setattr(suite, "install_autoupdate", fake_autoupdate)

    status = installer_module.install_suite(
        installer_module.SuiteInstallOptions(with_autoupdate=True)
    )

    assert status == 1
    assert calls == []


def test_linux_autoupdate_install_backs_up_existing_units(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setattr(suite, "is_windows", lambda: False)
    monkeypatch.setattr(suite.sys, "platform", "linux")
    monkeypatch.setattr(suite, "find_binary", lambda: "/tmp/vibeforcer")
    run_commands: list[list[str]] = []

    def fake_run(command: list[str], check: bool = False) -> subprocess.CompletedProcess[list[str]]:
        run_commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        suite.subprocess,
        "run",
        fake_run,
    )
    service = tmp_path / ".config/systemd/user/vibeforcer-auto-update.service"
    timer = tmp_path / ".config/systemd/user/vibeforcer-auto-update.timer"
    service.parent.mkdir(parents=True)
    service.write_text(f"# {suite._AUTOUPDATE_MARKER}\nexisting service\n", encoding="utf-8")
    timer.write_text(f"# {suite._AUTOUPDATE_MARKER}\nexisting timer\n", encoding="utf-8")

    assert suite.install_autoupdate(dry_run=False) == 0

    backups = sorted(service.parent.glob("*.vibeforcer-bak-*"))
    assert service.read_text(encoding="utf-8") != "existing service\n"
    assert timer.read_text(encoding="utf-8") != "existing timer\n"
    assert [backup.read_text(encoding="utf-8") for backup in backups] == [
        f"# {suite._AUTOUPDATE_MARKER}\nexisting service\n",
        f"# {suite._AUTOUPDATE_MARKER}\nexisting timer\n",
    ]
    assert run_commands == [["systemctl", "--user", "enable", "--now", "vibeforcer-auto-update.timer"]]


def test_windows_autoupdate_uninstall_refuses_unrecognized_script(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setattr(suite, "is_windows", lambda: True)
    def fake_user_data_dir(app_name: str) -> Path:
        return tmp_path / "LocalAppData" / app_name

    monkeypatch.setattr(suite, "user_data_dir", fake_user_data_dir)
    script = tmp_path / "LocalAppData/vibeforcer/vibeforcer-auto-update.ps1"
    script.parent.mkdir(parents=True)
    script.write_text("custom user script\n", encoding="utf-8")

    assert suite.uninstall_autoupdate(dry_run=False) == 1

    assert script.read_text(encoding="utf-8") == "custom user script\n"
    assert not sorted(script.parent.glob("*.vibeforcer-bak-*"))


def test_macos_autoupdate_uninstall_backs_up_owned_launch_agent(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(suite, "is_windows", lambda: False)
    monkeypatch.setattr(suite.sys, "platform", "darwin")
    monkeypatch.setattr(suite, "find_binary", lambda: "/usr/local/bin/vibeforcer")
    run_commands: list[list[str]] = []

    def fake_run(command: list[str], check: bool = False) -> subprocess.CompletedProcess[list[str]]:
        run_commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        suite.subprocess,
        "run",
        fake_run,
    )
    plan = suite.build_scheduler_plan()
    plan.target_path.parent.mkdir(parents=True)
    plan.target_path.write_text(plan.content, encoding="utf-8")

    assert suite.uninstall_autoupdate(dry_run=False) == 0

    backups = sorted(plan.target_path.parent.glob("*.vibeforcer-bak-*"))
    assert not plan.target_path.exists()
    assert len(backups) == 1
    assert "rocks.baked.vibeforcer.autoupdate" in backups[0].read_text(encoding="utf-8")
    assert run_commands == [["launchctl", "unload", "-w", str(plan.target_path)]]


def test_install_suite_dry_run_installs_detected_sites_without_writing(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".codex").mkdir()
    called: list[str] = []

    def fake_install(platform: str, dry_run: bool = False) -> int:
        called.append(f"{platform}:{dry_run}")
        return 0

    monkeypatch.setattr(installer_module, "install_platform", fake_install)

    status = installer_module.install_suite(installer_module.SuiteInstallOptions(dry_run=True))

    assert (status, called, "Would install: codex" in capsys.readouterr().out) == (
        0,
        [],
        True,
    )


def test_uninstall_suite_dry_run_reports_detected_sites_without_writing(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".claude").mkdir()
    called: list[str] = []

    def fake_uninstall(platform: str, dry_run: bool = False) -> int:
        called.append(f"{platform}:{dry_run}")
        return 0

    monkeypatch.setattr(installer_module, "uninstall_platform", fake_uninstall)

    status = installer_module.uninstall_suite(
        installer_module.SuiteUninstallOptions(dry_run=True)
    )

    output = capsys.readouterr().out
    assert (status, called, "Would uninstall: claude" in output) == (0, [], True)


def test_update_suite_dry_run_reports_package_update_and_hook_refresh(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(suite, "find_binary", lambda: "vibeforcer")

    def no_binary(_name: str) -> str | None:
        return None

    monkeypatch.setattr(suite.shutil, "which", no_binary)
    (tmp_path / ".claude").mkdir()

    status = installer_module.update_suite(
        dry_run=True, source="git+https://example.invalid/vf.git@main"
    )

    output = capsys.readouterr().out
    assert (
        status,
        "Would run:" in output,
        "pip install --upgrade" in output,
        "Refreshing claude hooks" in output,
        "Would install: claude" in output,
    ) == (0, True, True, True, True)
