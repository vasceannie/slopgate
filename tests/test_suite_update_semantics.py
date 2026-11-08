"""Suite update semantics: package update is safe unless hook refresh is explicit."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import slopgate.installer
import slopgate.installer._suite
from tests.native.hosts import FakeHosts, tree_digest

pytestmark = pytest.mark.usefixtures("native_hosts")

_UPDATE_SOURCE = "git+https://example.invalid/vf.git@main"
_INSTALLED_PLUGIN = "the plugin this device already runs\n"


def test_update_suite_dry_run_uses_uv_without_refreshing_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(slopgate.installer._suite, "find_binary", lambda: "slopgate")

    def uv_only(name: str) -> str | None:
        return "/usr/bin/uv" if name == "uv" else None

    monkeypatch.setattr(slopgate.installer._suite.shutil, "which", uv_only)
    (tmp_path / ".claude").mkdir()
    status = slopgate.installer.update_suite(
        slopgate.installer.SuiteUpdateOptions(
            dry_run=True, source="git+https://example.invalid/vf.git@main"
        )
    )
    output = capsys.readouterr().out
    assert (
        status,
        "Would run:" in output,
        "tool" in output and "install" in output and "--force" in output,
        "Hook refresh: skipped" in output,
        "Refreshing claude hooks" not in output,
    ) == (0, True, True, True, True)


def _explicit_refresh_preview(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    native_hosts: FakeHosts,
) -> tuple[int, str, str, str, list[str]]:
    monkeypatch.chdir(native_hosts.project)
    (native_hosts.home / ".claude").mkdir()
    monkeypatch.setattr(
        slopgate.installer._suite,
        "_package_update_command",
        lambda source: ["/usr/bin/uv", "tool", "install", "--force", source],
    )
    before = tree_digest(native_hosts.home)
    status = slopgate.installer.update_suite(
        slopgate.installer.SuiteUpdateOptions(
            dry_run=True,
            source=_UPDATE_SOURCE,
            refresh_hooks=True,
        )
    )
    output = capsys.readouterr().out
    return (
        status,
        output,
        before,
        tree_digest(native_hosts.home),
        native_hosts.mutating_calls(),
    )


def test_update_suite_refresh_hooks_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    native_hosts: FakeHosts,
) -> None:
    result = _explicit_refresh_preview(monkeypatch, capsys, native_hosts)

    assert (
        result[0],
        "Would run:" in result[1],
        "Refreshing claude (native plugin; user scope)" in result[1],
        "Installation mode: native plugin" in result[1],
        "Hook refresh: skipped" not in result[1],
    ) == (0, True, True, True, True), (
        "an explicit refresh preview should show native plugin work, not skip it"
    )


def test_update_suite_refresh_hooks_dry_run_is_read_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    native_hosts: FakeHosts,
) -> None:
    result = _explicit_refresh_preview(monkeypatch, capsys, native_hosts)

    assert (result[0], result[2] == result[3], result[4]) == (0, True, []), (
        "refresh dry-run must leave files unchanged and avoid native mutations"
    )


def test_update_suite_dry_run_falls_back_to_pip_without_refreshing_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(slopgate.installer._suite, "find_binary", lambda: "slopgate")

    def no_binary(_name: str) -> str | None:
        return None

    monkeypatch.setattr(slopgate.installer._suite.shutil, "which", no_binary)
    (tmp_path / ".claude").mkdir()
    status = slopgate.installer.update_suite(
        slopgate.installer.SuiteUpdateOptions(
            dry_run=True, source="git+https://example.invalid/vf.git@main"
        )
    )
    output = capsys.readouterr().out
    assert (
        status,
        "Would run:" in output,
        "pip" in output and "install" in output and "--upgrade" in output,
        "Hook refresh: skipped" in output,
        "Refreshing claude hooks" not in output,
    ) == (0, True, True, True, True)


def _record_package_updates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> list[list[str]]:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setattr(slopgate.installer._suite, "find_binary", lambda: "slopgate")
    monkeypatch.setattr(
        slopgate.installer._suite.shutil, "which", lambda _name: "/usr/bin/uv"
    )
    commands: list[list[str]] = []

    def record_update(
        command: list[str], **_options: object
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(slopgate.installer._suite.subprocess, "run", record_update)
    return commands


def test_package_update_only_replaces_the_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands = _record_package_updates(tmp_path, monkeypatch)

    status = slopgate.installer.update_suite(
        slopgate.installer.SuiteUpdateOptions(source=_UPDATE_SOURCE)
    )

    assert (status, commands) == (
        0,
        [["/usr/bin/uv", "tool", "install", "--force", _UPDATE_SOURCE]],
    ), "a successful update must run one package install and report success"


def _install_opencode_plugin_file() -> Path:
    sites = slopgate.installer._suite.discover_install_sites(include_missing=True)
    plugin = next(site.path for site in sites if site.platform == "opencode")
    plugin.parent.mkdir(parents=True)
    plugin.write_text(_INSTALLED_PLUGIN, encoding="utf-8")
    return plugin


def test_package_update_leaves_installed_opencode_plugin_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record_package_updates(tmp_path, monkeypatch)
    plugin = _install_opencode_plugin_file()

    slopgate.installer.update_suite(
        slopgate.installer.SuiteUpdateOptions(source=_UPDATE_SOURCE)
    )

    assert plugin.read_text(encoding="utf-8") == _INSTALLED_PLUGIN, (
        "a package update must not rewrite the plugin a host has loaded"
    )


@pytest.mark.skipif(
    sys.platform == "win32", reason="Windows has no scheduled auto-updater"
)
def test_scheduled_update_never_refreshes_hooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(slopgate.installer._suite, "find_binary", lambda: "slopgate")

    plan = slopgate.installer._suite.build_scheduler_plan(_UPDATE_SOURCE)

    assert _UPDATE_SOURCE in plan.content, "the schedule must run the package update"
    assert "--refresh-hooks" not in plan.content, (
        "an unattended run must not replace plugins with whatever the source ships"
    )
