from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import vibeforcer.installer as installer_module
import vibeforcer.util.platform as platform_utils
from pytest import CaptureFixture, MonkeyPatch


def _dry_run_install_json(
    platform: str,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    *,
    binary: str | None = "vibeforcer",
    windows: bool = False,
) -> dict[str, Any]:
    def which(name: str) -> str | None:
        return binary if name == "vibeforcer" else None

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(installer_module, "is_windows", lambda: windows)
    monkeypatch.setattr(installer_module.shutil, "which", which)

    assert installer_module.install_platform(platform, dry_run=True) == 0
    output = capsys.readouterr().out
    return json.loads(output[output.index("{") :])


def _hook_commands(hooks: dict[str, Any]) -> Iterable[str]:
    for entries in hooks.values():
        for entry in entries:
            for hook in entry["hooks"]:
                command = hook.get("command")
                if isinstance(command, str):
                    yield command


def test_codex_hooks_are_bash_only(
    capsys: CaptureFixture[str], monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    data = _dry_run_install_json("codex", capsys, monkeypatch, tmp_path)
    hooks = data["hooks"]
    pre = hooks["PreToolUse"][0]
    post = hooks["PostToolUse"][0]
    pre_matcher = str(pre.get("matcher", ""))
    post_matcher = str(post.get("matcher", ""))
    assert pre_matcher == "Bash"
    assert post_matcher == "Bash"
    assert "PermissionRequest" not in hooks


def test_claude_hooks_include_cwd_changed(
    capsys: CaptureFixture[str], monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    data = _dry_run_install_json("claude", capsys, monkeypatch, tmp_path)
    assert "CwdChanged" in data["hooks"]


def test_windows_codex_install_emits_powershell_hook_commands(
    capsys: CaptureFixture[str], monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    data = _dry_run_install_json(
        "codex",
        capsys,
        monkeypatch,
        tmp_path,
        binary=r"C:\Users\Trav App\AppData\Local\Programs\Python\Scripts\vibeforcer.exe",
        windows=True,
    )
    commands = list(_hook_commands(data["hooks"]))
    assert commands
    for command in commands:
        assert command.startswith("powershell.exe ")
        assert "-NoProfile" in command
        assert "-NonInteractive" in command
        assert "-Command" in command
        assert "C:\\Users\\Trav App\\AppData" in command
        assert "handle" in command
        assert "codex" in command


def test_claude_install_falls_back_to_python_module_invocation(
    capsys: CaptureFixture[str], monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    data = _dry_run_install_json(
        "claude",
        capsys,
        monkeypatch,
        tmp_path,
        binary=None,
    )
    commands = list(_hook_commands(data["hooks"]))
    assert commands
    assert all(" -m vibeforcer handle" in command for command in commands)


def test_opencode_install_bakes_windows_binary_into_plugin(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    binary = r"C:\Users\Trav App\AppData\Local\Programs\Python\Scripts\vibeforcer.exe"

    def which(name: str) -> str | None:
        return binary if name == "vibeforcer" else None

    monkeypatch.setattr(installer_module, "is_windows", lambda: True)
    monkeypatch.setattr(platform_utils, "is_windows", lambda: True)
    monkeypatch.setattr(installer_module.shutil, "which", which)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))

    assert installer_module.install_platform("opencode", dry_run=False) == 0

    plugin_path = tmp_path / "Roaming" / "opencode" / "plugins" / "vibeforcer-plugin.ts"
    plugin = plugin_path.read_text(encoding="utf-8")
    assert "__VIBEFORCER_BIN__" not in plugin
    assert json.dumps(binary) in plugin
    assert 'Bun.env.VIBEFORCER_BIN ||' in plugin


def test_opencode_plugin_treats_empty_success_as_allow_noop() -> None:
    from vibeforcer.resources import resource_path

    plugin = resource_path("opencode_plugin.ts").read_text(encoding="utf-8")
    assert "empty enforcer response" not in plugin
    assert "if (!trimmed) return null" in plugin
    assert "exits 0 with no stdout" in plugin
