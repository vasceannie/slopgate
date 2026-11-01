from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from slopgate.cli.check import cmd_check
from slopgate.installer import _opencode
import slopgate.installer._shared
from slopgate.util import platform


_V1_PLUGIN = (
    "/** OpenCode Slopgate Plugin */\n"
    'const SLOPGATE_BIN = "slopgate"\n'
    "export const EnforcerPlugin = async () => ({})\n"
)


def _isolated_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    return tmp_path / ".config" / "opencode" / "plugins" / "slopgate-plugin.ts"


def test_v1_plugin_is_reported_as_inert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _isolated_user_config(tmp_path, monkeypatch)
    target.parent.mkdir(parents=True)
    target.write_text(_V1_PLUGIN, encoding="utf-8")

    inert = _opencode.inert_opencode_plugins(tmp_path / "project")

    assert inert == [target], "the V2 host refuses a V1 export, leaving no enforcement"


def test_installed_v2_plugin_is_not_reported_as_inert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolated_user_config(tmp_path, monkeypatch)
    assert _opencode.install_opencode(dry_run=False) == 0, "install must succeed"

    inert = _opencode.inert_opencode_plugins(tmp_path / "project")

    assert inert == [], "a freshly rendered plugin must count as healthy"


def test_unowned_plugin_is_not_reported_as_inert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _isolated_user_config(tmp_path, monkeypatch)
    target.parent.mkdir(parents=True)
    target.write_text("export const Mine = 1\n", encoding="utf-8")

    inert = _opencode.inert_opencode_plugins(tmp_path / "project")

    assert inert == [], "files slopgate does not own are not its health signal"


def _project_with_inert_user_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    target = _isolated_user_config(tmp_path, monkeypatch)
    target.parent.mkdir(parents=True)
    target.write_text(_V1_PLUGIN, encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    return project, target


def test_check_warning_names_inert_plugin_and_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project, target = _project_with_inert_user_plugin(tmp_path, monkeypatch)

    cmd_check(argparse.Namespace(path=str(project)))

    stderr = capsys.readouterr().err
    assert str(target) in stderr, "the warning must name the inert plugin"
    assert "slopgate install opencode" in stderr, "it must state the remedy"


def test_check_output_stays_parseable_with_inert_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project, _target = _project_with_inert_user_plugin(tmp_path, monkeypatch)

    status = cmd_check(argparse.Namespace(path=str(project)))

    assert status == 0, "health warnings must not change the check exit status"
    assert json.loads(capsys.readouterr().out)["path"] == str(project), (
        "stdout must stay parseable JSON for scripts"
    )


def test_both_scope_install_warns_project_copy_loses_duplicate_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    user_target = _isolated_user_config(tmp_path, monkeypatch)
    project = tmp_path / "project"
    project.mkdir()

    status = _opencode.install_opencode(
        dry_run=False, scope="both", project_root=project
    )

    output = capsys.readouterr().out
    assert status == 0, "both-scope install must still succeed"
    assert "Duplicate plugin ID: slopgate" in output, (
        "the host keeps only one plugin per ID, which the operator must be told"
    )
    assert str(user_target) in output, "the note must name the copy that stays active"


def test_single_scope_install_has_no_duplicate_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _isolated_user_config(tmp_path, monkeypatch)

    _opencode.install_opencode(dry_run=False)

    assert "Duplicate plugin ID" not in capsys.readouterr().out, (
        "one installed copy cannot collide"
    )


def test_opencode_installer_uses_appdata_plugin_dir_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    monkeypatch.setattr(platform, "is_windows", lambda: True)
    monkeypatch.setenv("APPDATA", str(appdata))
    assert (
        _opencode.opencode_user_plugin_path()
        == appdata / "opencode" / "plugins" / "slopgate-plugin.ts"
    ), "Windows installs should use the AppData OpenCode plugin directory"


def test_opencode_install_backs_up_existing_plugin_before_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/Slopgate Bin/slopgate"
    )
    target = tmp_path / ".config" / "opencode" / "plugins" / "slopgate-plugin.ts"
    target.parent.mkdir(parents=True)
    target.write_text("custom plugin\n", encoding="utf-8")
    assert _opencode.install_opencode(dry_run=False) == 0, (
        "install should succeed before verifying its backup"
    )
    backups = sorted(target.parent.glob("slopgate-plugin.ts.slopgate-bak-*"))
    assert len(backups) == 1, "install should create exactly one plugin backup"
    assert backups[0].read_text(encoding="utf-8") == "custom plugin\n", (
        "the backup should preserve the existing plugin"
    )


def _plant_opencode_user_leaf_symlink(tmp_path: Path) -> tuple[Path, Path]:
    outside = tmp_path / "outside" / "secret.ts"
    outside.parent.mkdir()
    outside.write_text("KEEP\n", encoding="utf-8")
    target = tmp_path / ".config" / "opencode" / "plugins" / "slopgate-plugin.ts"
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)
    return target, outside


def test_opencode_user_install_refuses_leaf_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    target, outside = _plant_opencode_user_leaf_symlink(tmp_path)
    assert _opencode.install_opencode(dry_run=False) == 1, (
        "user install must refuse a leaf symlink"
    )
    assert outside.read_text(encoding="utf-8") == "KEEP\n", (
        "external symlink targets must remain unchanged"
    )
    assert target.is_symlink(), "the planted leaf symlink must not be replaced"


def test_opencode_uninstall_removes_legacy_owned_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    target = tmp_path / ".config" / "opencode" / "plugins" / "slopgate-plugin.ts"
    target.parent.mkdir(parents=True)
    target.write_text(
        '/* OpenCode Slopgate Plugin */\nconst SLOPGATE_BIN = "slopgate";\n',
        encoding="utf-8",
    )

    assert _opencode.uninstall_opencode(dry_run=False) == 0, (
        "legacy owned plugins must remain uninstallable"
    )
    assert not target.exists(), "legacy owned plugin should be removed"


def test_opencode_uninstall_refuses_unrecognized_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    target = tmp_path / ".config" / "opencode" / "plugins" / "slopgate-plugin.ts"
    target.parent.mkdir(parents=True)
    target.write_text("custom plugin\n", encoding="utf-8")
    assert _opencode.uninstall_opencode(dry_run=False) == 1, (
        "uninstall should refuse an unrecognized plugin"
    )
    assert target.read_text(encoding="utf-8") == "custom plugin\n", (
        "uninstall should preserve an unrecognized plugin"
    )


def test_opencode_uninstall_refuses_custom_plugin_with_incidental_marker_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    target = tmp_path / ".config" / "opencode" / "plugins" / "slopgate-plugin.ts"
    target.parent.mkdir(parents=True)
    target.write_text(
        "// docs mention slopgate handle --platform opencode, but this is custom\n",
        encoding="utf-8",
    )
    assert _opencode.uninstall_opencode(dry_run=False) == 1, (
        "uninstall should refuse a custom plugin with incidental marker text"
    )
    assert target.exists(), "custom plugin should remain after refused uninstall"
    assert "this is custom" in target.read_text(encoding="utf-8"), (
        "refused uninstall should preserve custom plugin content"
    )
