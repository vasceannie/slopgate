"""Scheduler install/uninstall tests split from test_suite_autoupdate."""

from __future__ import annotations
import subprocess
import pytest
from pathlib import Path
import slopgate.installer
import slopgate.installer._suite
from slopgate.cli.commands import cmd_install
from slopgate.cli.parsers import build_parser
from tests.test_suite_autoupdate import (
    _patch_linux_installer_config_dirs,
    linux_autoupdate_units,
    macos_autoupdate_context,
    record_suite_subprocess_run,
    windows_owned_task_install_snapshot,
)
from tests.support import SKIP_DARWIN_ONLY, SKIP_LINUX_ONLY, SKIP_WINDOWS_ONLY


@SKIP_LINUX_ONLY
def test_linux_autoupdate_install_refuses_unowned_existing_units(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, timer = linux_autoupdate_units(tmp_path, monkeypatch)
    service.write_text("custom service\n", encoding="utf-8")
    timer.write_text("custom timer\n", encoding="utf-8")
    assert (
        slopgate.installer._suite.install_autoupdate(dry_run=False),
        service.read_text(encoding="utf-8"),
        timer.read_text(encoding="utf-8"),
        sorted(service.parent.glob("*.slopgate-bak-*")),
    ) == (1, "custom service\n", "custom timer\n", [])


@SKIP_LINUX_ONLY
def test_autoupdate_uninstall_refuses_incidental_scheduler_marker_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config_home = _patch_linux_installer_config_dirs(monkeypatch, tmp_path)
    timer = config_home / "systemd/user/slopgate-auto-update.timer"
    timer.parent.mkdir(parents=True)
    timer.write_text(
        "# custom comment mentions slopgate-auto-update\n[Timer]\n", encoding="utf-8"
    )
    assert slopgate.installer._suite.uninstall_autoupdate(dry_run=False) == 1
    assert timer.exists()
    assert not sorted(timer.parent.glob("*.slopgate-bak-*"))


def test_install_with_autoupdate_stops_when_platform_install_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    calls: list[bool] = []

    def fail_install(_platform: str, dry_run: bool = False, **_kwargs: object) -> int:
        return 1

    def fake_autoupdate(**_kwargs: object) -> int:
        calls.append(True)
        return 0

    monkeypatch.setattr(slopgate.installer, "install_platform", fail_install)
    monkeypatch.setattr(
        slopgate.installer._suite, "install_autoupdate", fake_autoupdate
    )
    args = build_parser().parse_args(["install", "claude"])
    assert args.func is cmd_install
    assert cmd_install(args) == 1
    assert calls == []


def test_install_suite_with_autoupdate_stops_when_platform_install_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".claude").mkdir()
    calls: list[bool] = []

    def fail_install(_platform: str, dry_run: bool = False, **_kwargs: object) -> int:
        return 1

    def fake_autoupdate(**_kwargs: object) -> int:
        calls.append(True)
        return 0

    monkeypatch.setattr(slopgate.installer, "install_platform", fail_install)
    monkeypatch.setattr(
        slopgate.installer._suite, "install_autoupdate", fake_autoupdate
    )
    status = slopgate.installer.install_suite(
        slopgate.installer.SuiteInstallOptions(with_autoupdate=True)
    )
    assert status == 1
    assert calls == []


def _linux_owned_unit_backup_snapshot(
    service: Path, timer: Path, run_commands: list[list[str]]
) -> dict[str, object]:
    status = slopgate.installer._suite.install_autoupdate(dry_run=False)
    backups = sorted(service.parent.glob("*.slopgate-bak-*"))
    return {
        "status": status,
        "service_changed": service.read_text(encoding="utf-8") != "existing service\n",
        "timer_changed": timer.read_text(encoding="utf-8") != "existing timer\n",
        "backup_texts": [backup.read_text(encoding="utf-8") for backup in backups],
        "run_commands": run_commands,
    }


@SKIP_LINUX_ONLY
def test_linux_autoupdate_install_backs_up_existing_units(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, timer = linux_autoupdate_units(tmp_path, monkeypatch)
    monkeypatch.setattr(
        slopgate.installer._suite, "find_binary", lambda: "/tmp/slopgate"
    )
    run_commands = record_suite_subprocess_run(monkeypatch)
    service.write_text(
        f"# {slopgate.installer._suite.AUTOUPDATE_MARKER}\nexisting service\n",
        encoding="utf-8",
    )
    timer.write_text(
        f"# {slopgate.installer._suite.AUTOUPDATE_MARKER}\nexisting timer\n",
        encoding="utf-8",
    )
    snapshot = _linux_owned_unit_backup_snapshot(service, timer, run_commands)
    assert snapshot == {
        "status": 0,
        "service_changed": True,
        "timer_changed": True,
        "backup_texts": [
            f"# {slopgate.installer._suite.AUTOUPDATE_MARKER}\nexisting service\n",
            f"# {slopgate.installer._suite.AUTOUPDATE_MARKER}\nexisting timer\n",
        ],
        "run_commands": [
            ["systemctl", "--user", "enable", "--now", "slopgate-auto-update.timer"]
        ],
    }


def _windows_autoupdate_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setattr(slopgate.installer._suite, "is_windows", lambda: True)
    monkeypatch.setattr(
        slopgate.installer._suite, "find_binary", lambda: "C:\\Tools\\slopgate.exe"
    )

    def fake_user_data_dir(app_name: str) -> Path:
        return tmp_path / "LocalAppData" / app_name

    monkeypatch.setattr(slopgate.installer._suite, "user_data_dir", fake_user_data_dir)
    return tmp_path / "LocalAppData/slopgate/slopgate-auto-update.ps1"


@SKIP_WINDOWS_ONLY
def test_windows_autoupdate_uninstall_refuses_unrecognized_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _windows_autoupdate_context(tmp_path, monkeypatch)
    script.parent.mkdir(parents=True)
    script.write_text("custom user script\n", encoding="utf-8")
    assert slopgate.installer._suite.uninstall_autoupdate(dry_run=False) == 1
    assert script.read_text(encoding="utf-8") == "custom user script\n"
    assert not sorted(script.parent.glob("*.slopgate-bak-*"))


@SKIP_WINDOWS_ONLY
def test_windows_autoupdate_install_refuses_existing_unowned_task_before_force_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _windows_autoupdate_context(tmp_path, monkeypatch)
    run_commands: list[list[str]] = []

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        run_commands.append(command)
        if command[:2] == ["schtasks", "/Query"]:
            return slopgate.installer._suite.subprocess.CompletedProcess(
                command,
                0,
                stdout="<Task><Actions><Exec><Command>custom.exe</Command></Exec></Actions></Task>",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(slopgate.installer._suite.subprocess, "run", fake_run)
    assert slopgate.installer._suite.install_autoupdate(dry_run=False) == 1
    assert run_commands == [
        ["schtasks", "/Query", "/TN", "Slopgate Auto Update", "/XML"]
    ]
    assert not script.exists()


@SKIP_WINDOWS_ONLY
def test_windows_autoupdate_install_exports_owned_existing_task_before_force_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _windows_autoupdate_context(tmp_path, monkeypatch)
    script.parent.mkdir(parents=True)
    script.write_text(
        f"# {slopgate.installer._suite.AUTOUPDATE_MARKER}\nold script\n",
        encoding="utf-8",
    )
    xml = (
        f"<Task><Actions><Exec><Arguments>{script}</Arguments></Exec></Actions></Task>"
    )
    snapshot = windows_owned_task_install_snapshot(script, monkeypatch, xml=xml)
    assert snapshot == {
        "status": 0,
        "backup_count": 1,
        "backup_xml": xml,
        "query_command": ["schtasks", "/Query", "/TN", "Slopgate Auto Update", "/XML"],
        "create_prefix": ["schtasks", "/Create", "/F"],
    }


def _macos_uninstall_backup_snapshot(
    run_commands: list[list[str]],
) -> dict[str, object]:
    plan = slopgate.installer._suite.build_scheduler_plan()
    plan.target_path.parent.mkdir(parents=True)
    plan.target_path.write_text(plan.content, encoding="utf-8")
    status = slopgate.installer._suite.uninstall_autoupdate(dry_run=False)
    backups = sorted(plan.target_path.parent.glob("*.slopgate-bak-*"))
    return {
        "status": status,
        "exists": plan.target_path.exists(),
        "backup_count": len(backups),
        "marker_present": "rocks.baked.slopgate.autoupdate"
        in backups[0].read_text(encoding="utf-8"),
        "run_commands": run_commands,
        "target_path": str(plan.target_path),
    }


@SKIP_DARWIN_ONLY
def test_macos_autoupdate_uninstall_backs_up_owned_launch_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    macos_autoupdate_context(tmp_path, monkeypatch)
    snapshot = _macos_uninstall_backup_snapshot(
        record_suite_subprocess_run(monkeypatch)
    )
    assert {
        "status": snapshot["status"],
        "exists": snapshot["exists"],
        "backup_count": snapshot["backup_count"],
        "marker_present": snapshot["marker_present"],
        "run_commands": snapshot["run_commands"],
    } == {
        "status": 0,
        "exists": False,
        "backup_count": 1,
        "marker_present": True,
        "run_commands": [["launchctl", "unload", "-w", snapshot["target_path"]]],
    }


def test_install_suite_dry_run_installs_detected_sites_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".codex").mkdir()
    called: list[str] = []

    def fake_install(platform: str, dry_run: bool = False) -> int:
        called.append(f"{platform}:{dry_run}")
        return 0

    monkeypatch.setattr(slopgate.installer, "install_platform", fake_install)
    status = slopgate.installer.install_suite(
        slopgate.installer.SuiteInstallOptions(dry_run=True)
    )
    assert (status, called, "Would install: codex" in capsys.readouterr().out) == (
        0,
        [],
        True,
    )


def test_uninstall_suite_dry_run_reports_detected_sites_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".claude").mkdir()
    called: list[str] = []

    def fake_uninstall(platform: str, dry_run: bool = False) -> int:
        called.append(f"{platform}:{dry_run}")
        return 0

    monkeypatch.setattr(slopgate.installer, "uninstall_platform", fake_uninstall)
    status = slopgate.installer.uninstall_suite(
        slopgate.installer.SuiteUninstallOptions(dry_run=True)
    )
    output = capsys.readouterr().out
    assert (status, called, "Would uninstall: claude" in output) == (0, [], True)


class TestPathAppearsInTaskXml:
    """Test suite_autoupdate_windows.path_appears_in_task_xml with edge cases."""

    def test_returns_false_for_empty_xml(self) -> None:
        from slopgate.installer._suite_autoupdate_windows import (
            path_appears_in_task_xml,
        )
        from pathlib import Path

        result = path_appears_in_task_xml(Path("C:\\slopgate.exe"), "")
        assert result is False, "Empty XML should return False"

    def test_returns_false_for_malformed_xml(self) -> None:
        from slopgate.installer._suite_autoupdate_windows import (
            path_appears_in_task_xml,
        )
        from pathlib import Path

        result = path_appears_in_task_xml(
            Path("C:\\slopgate.exe"), "<Malformed>no closing tag"
        )
        assert result is False, "Malformed XML should return False"

    def test_returns_false_for_xml_without_path(self) -> None:
        from slopgate.installer._suite_autoupdate_windows import (
            path_appears_in_task_xml,
        )
        from pathlib import Path

        result = path_appears_in_task_xml(
            Path("C:\\slopgate.exe"), "<Task><Actions></Actions></Task>"
        )
        assert result is False, "XML without matching path should return False"
