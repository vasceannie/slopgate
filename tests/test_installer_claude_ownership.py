from __future__ import annotations

import json
from pathlib import Path

import pytest

import slopgate.installer
import slopgate.installer._shared
from slopgate.installer.native.migration import extract_owned_hooks
from tests.claude_installer_support import claude_harness, seed_hook_settings


def _prepare_claude_reinstall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, Path]:
    harness = claude_harness(tmp_path, monkeypatch)
    old_hook = slopgate.installer._shared.hook_command(
        "C:\\\\Old Tools\\\\slopgate.exe", "handle", windows=True
    )
    settings_path = seed_hook_settings(harness, "my-slopgate-helper handle", old_hook)
    result = slopgate.installer.install_claude(project_root=harness.project)
    return result, settings_path


def _hook_commands(settings_path: Path) -> list[str]:
    hooks = json.loads(settings_path.read_text(encoding="utf-8"))["hooks"]
    return [
        hook["command"]
        for entry in hooks["PreToolUse"]
        for hook in entry.get("hooks", [])
    ]


def test_claude_reinstall_retires_owned_powershell_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, settings_path = _prepare_claude_reinstall(tmp_path, monkeypatch)
    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    assert (result, extract_owned_hooks(settings.get("hooks"))) == (0, {}), (
        "native install should succeed and remove the old owned PowerShell hook"
    )


def test_claude_reinstall_preserves_unrelated_slopgate_named_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, settings_path = _prepare_claude_reinstall(tmp_path, monkeypatch)

    assert (result, _hook_commands(settings_path)) == (
        0,
        ["my-slopgate-helper handle"],
    ), "legacy cutover must preserve unrelated Slopgate-named helper commands"


def test_claude_reinstall_preserves_unrelated_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, settings_path = _prepare_claude_reinstall(tmp_path, monkeypatch)
    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    assert (result, settings["unrelatedSetting"]) == (0, True), (
        "legacy cutover must preserve the exact unrelated setting value"
    )


def test_claude_uninstall_removes_owned_hook_and_preserves_user_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = claude_harness(tmp_path, monkeypatch)
    old_hook = slopgate.installer._shared.hook_command(
        "C:\\\\Old Tools\\\\slopgate.exe", "handle", windows=True
    )
    settings_path = seed_hook_settings(harness, "slopgate-doc handle", old_hook)
    result = slopgate.installer.uninstall_claude(project_root=harness.project)

    assert (result, _hook_commands(settings_path)) == (
        0,
        ["slopgate-doc handle"],
    ), "legacy-only uninstall must remove only the exact owned command"
