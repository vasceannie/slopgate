from __future__ import annotations

import json
import sys
from pathlib import Path

from pytest import MonkeyPatch

import slopgate.installer
import slopgate.installer._opencode
import slopgate.installer._shared
import slopgate.util.platform


def test_opencode_install_bakes_windows_binary_into_plugin(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    binary = (
        "C:\\Users\\Trav App\\AppData\\Local\\Programs\\Python\\Scripts\\slopgate.exe"
    )

    def which(name: str) -> str | None:
        return binary if name == "slopgate" else None

    def run_probe(
        command: list[str], **_kwargs: object
    ) -> slopgate.installer._shared.subprocess.CompletedProcess[list[str]]:
        return slopgate.installer._shared.subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(slopgate.util.platform, "is_windows", lambda: True)
    monkeypatch.setattr(slopgate.installer._shared.shutil, "which", which)
    monkeypatch.setattr(slopgate.installer._shared.subprocess, "run", run_probe)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert slopgate.installer.install_platform("opencode", dry_run=False) == 0
    plugin_path = tmp_path / "Roaming" / "opencode" / "plugins" / "slopgate-plugin.ts"
    plugin = plugin_path.read_text(encoding="utf-8")
    assert "__SLOPGATE_BIN__" not in plugin
    assert json.dumps([binary]) in plugin
    assert "Bun.env.SLOPGATE_BIN ? [Bun.env.SLOPGATE_BIN] :" in plugin


def test_opencode_plugin_falls_back_to_python_module_invocation() -> None:
    from slopgate.resources import resource_path

    template = resource_path("opencode_plugin.ts").read_text(encoding="utf-8")
    plugin = slopgate.installer._opencode.render_opencode_plugin(
        template, sys.executable
    )
    assert "__SLOPGATE_BIN__" not in plugin, "placeholder should be fully rendered"
    assert json.dumps([sys.executable, "-m", "slopgate"]) in plugin, (
        "python fallback must invoke slopgate as a module"
    )
    assert '[...SLOPGATE_ARGV, "handle", "--platform", "opencode"]' in plugin, (
        "OpenCode plugin must spawn the rendered argv prefix"
    )
    assert f'{json.dumps(sys.executable)}, "handle"' not in plugin, (
        "python fallback must not execute `python handle`"
    )


def test_opencode_plugin_treats_empty_success_as_allow_noop() -> None:
    from slopgate.resources import resource_path

    plugin = resource_path("opencode_plugin.ts").read_text(encoding="utf-8")
    assert "empty enforcer response" not in plugin
    assert "if (!trimmed) return null" in plugin
    assert "exits 0 with no stdout" in plugin
