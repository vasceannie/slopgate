from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import cast

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "dashboard" / "scripts"
SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SRC_DIR))

_resources = importlib.import_module("forcedash_server.resources")
read_remote_script = _resources.read_remote_script

HARNESS_STATUS_SCRIPT = "harness_status.py.txt"
CODEX_EVENTS = [
    "SessionStart",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "UserPromptSubmit",
    "Stop",
]
FAKE_OPENCODE_CONFIG = {
    "plugin": ["slopgate-plugin.ts"],
    "provider": {"api_key": "live-secret", "name": "example"},
}


def _run_harness_status_with_fake_opencode_config(home: Path) -> dict[str, object]:
    script = read_remote_script(HARNESS_STATUS_SCRIPT)
    bootstrap = """
import json
import urllib.request

class FakeResponse:
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def read(self):
        return json.dumps(FAKE_OPENCODE_CONFIG).encode("utf-8")

urllib.request.urlopen = lambda *_args, **_kwargs: FakeResponse()
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"FAKE_OPENCODE_CONFIG = {FAKE_OPENCODE_CONFIG!r}\n{bootstrap}\n{script}",
        ],
        check=True,
        capture_output=True,
        env={"HOME": str(home)},
        text=True,
    )
    parsed: object = json.loads(result.stdout)
    assert isinstance(parsed, dict), "Expected harness status script to emit an object"
    return cast(dict[str, object], parsed)


def _opencode_platform(payload: dict[str, object]) -> dict[str, object]:
    platforms = cast(list[dict[str, object]], payload["platforms"])
    opencode = platforms[2]
    assert opencode["id"] == "opencode", "Expected OpenCode platform entry"
    return opencode


def _codex_platform(payload: dict[str, object]) -> dict[str, object]:
    platforms = cast(list[dict[str, object]], payload["platforms"])
    codex = platforms[1]
    assert codex["id"] == "codex", "Expected Codex platform entry"
    return codex


def _write_codex_install(home: Path, config_text: str) -> None:
    codex_dir = home / ".codex"
    codex_dir.mkdir()
    hook_command = "slopgate handle --platform codex"
    hooks = {event: [{"hooks": [{"command": hook_command}]}] for event in CODEX_EVENTS}
    (codex_dir / "hooks.json").write_text(
        json.dumps({"hooks": hooks}),
        encoding="utf-8",
    )
    (codex_dir / "config.toml").write_text(config_text, encoding="utf-8")


def test_harness_status_checks_live_opencode_config_and_redacts_provider_secret(
    tmp_path: Path,
) -> None:
    payload = _run_harness_status_with_fake_opencode_config(tmp_path)
    opencode = _opencode_platform(payload)
    live_config = cast(dict[str, object], opencode["live_config"])
    redacted = cast(dict[str, object], live_config["redacted_config"])
    provider = cast(dict[str, object], redacted["provider"])

    assert live_config["reachable"] is True, "Expected live OpenCode config probe"
    assert live_config["plugin_registered"] is True, (
        "Expected merged OpenCode server config to register Slopgate plugin"
    )
    assert provider["api_key"] == "[redacted]", (
        "Expected provider API keys to be redacted before sharing"
    )
    assert provider["name"] == "example", (
        "Expected non-sensitive provider settings to remain visible"
    )


def test_harness_status_accepts_current_codex_hooks_feature_key(
    tmp_path: Path,
) -> None:
    _write_codex_install(tmp_path, "[features]\nhooks = true\n")
    payload = _run_harness_status_with_fake_opencode_config(tmp_path)
    codex = _codex_platform(payload)

    assert codex["status"] == "installed", (
        "Expected canonical features.hooks=true to mark installed Codex hooks"
    )
    assert codex["feature_flag_enabled"] is True, (
        "Expected harness status to recognize the current Codex hooks flag"
    )
    assert codex["missing_events"] == [], (
        "Expected complete Codex hook event coverage in the synthetic install"
    )
