from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import tomli
from pytest import CaptureFixture, MonkeyPatch

import vibeforcer.installer as installer_module
import vibeforcer.installer._shared as installer_shared
import vibeforcer.util.platform as platform_utils


def _hook_builder(name: str) -> Any:
    return getattr(installer_module, name)


def _assert_canonical_codex_hooks_feature(config: dict[str, Any]) -> None:
    features = config["features"]
    assert features["hooks"] is True
    assert "codex_hooks" not in features


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
    monkeypatch.setattr(installer_shared, "is_windows", lambda: windows)
    monkeypatch.setattr(installer_shared.shutil, "which", which)

    assert installer_module.install_platform(platform, dry_run=True) == 0
    output = capsys.readouterr().out
    return json.loads(output[output.index("{") :])


def _all_hook_commands(hooks: dict[str, Any]) -> Iterable[str]:
    for entries in hooks.values():
        for entry in entries:
            for hook in entry["hooks"]:
                command = hook.get("command")
                if isinstance(command, str):
                    yield command


def _hook_commands(hooks: dict[str, Any], event_name: str = "PreToolUse") -> list[str]:
    entries = hooks[event_name]
    assert isinstance(entries, list)
    commands: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        hook_entries = entry.get("hooks")
        if not isinstance(hook_entries, list):
            continue
        for hook in hook_entries:
            if not isinstance(hook, dict):
                continue
            command = hook.get("command")
            if isinstance(command, str):
                commands.append(command)
    return commands


def test_codex_hooks_cover_current_tool_events() -> None:
    hooks = _hook_builder("_codex_hooks_block")("vibeforcer")
    session_start = hooks["SessionStart"][0]
    pre = hooks["PreToolUse"][0]
    post = hooks["PostToolUse"][0]
    permission = hooks["PermissionRequest"][0]
    session_start_matcher = str(session_start.get("matcher", ""))
    pre_matcher = str(pre.get("matcher", ""))
    post_matcher = str(post.get("matcher", ""))
    permission_matcher = str(permission.get("matcher", ""))
    required_tools = {"Bash", "apply_patch", "Edit", "Write"}
    missing_tools_by_matcher = {
        "PreToolUse": sorted(tool for tool in required_tools if tool not in pre_matcher),
        "PostToolUse": sorted(tool for tool in required_tools if tool not in post_matcher),
        "PermissionRequest": sorted(
            tool for tool in required_tools if tool not in permission_matcher
        ),
    }

    assert missing_tools_by_matcher == {
        "PreToolUse": [],
        "PostToolUse": [],
        "PermissionRequest": [],
    }
    assert all(
        source in session_start_matcher for source in ("startup", "resume", "clear")
    )


def test_codex_hooks_are_bash_only(
    capsys: CaptureFixture[str], monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    data = _dry_run_install_json("codex", capsys, monkeypatch, tmp_path)
    hooks = data["hooks"]
    commands = list(_all_hook_commands(hooks))
    assert (
        bool(commands),
        all(command.startswith("vibeforcer ") for command in commands),
        all(" handle" in command for command in commands),
        all("powershell.exe" not in command for command in commands),
    ) == (True, True, True, True)


def test_codex_installer_enables_current_toml_feature(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                'model = "gpt-5"',
                "",
                "[features]",
                "plugin_hooks = true",
                "codex_hooks = false # stale",
                "",
                '[projects."/tmp/example"]',
                'trust_level = "trusted"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    installer_module._enable_codex_hooks_toml(config_path)

    parsed = tomli.loads(config_path.read_text(encoding="utf-8"))
    _assert_canonical_codex_hooks_feature(parsed)
    assert parsed["features"]["plugin_hooks"] is True
    assert parsed["projects"]["/tmp/example"]["trust_level"] == "trusted"


def test_codex_installer_creates_toml_features_section(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"

    installer_module._enable_codex_hooks_toml(config_path)

    parsed = tomli.loads(config_path.read_text(encoding="utf-8"))
    _assert_canonical_codex_hooks_feature(parsed)
    assert config_path.exists()


def test_codex_install_writes_hooks_and_toml_feature(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(installer_module, "_find_binary", lambda: "vibeforcer")

    assert installer_module._install_codex(dry_run=False) == 0

    hooks = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
    config = tomli.loads((tmp_path / ".codex" / "config.toml").read_text())
    assert "PermissionRequest" in hooks["hooks"]
    _assert_canonical_codex_hooks_feature(config)


def test_claude_install_refuses_invalid_existing_json(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("{not-json", encoding="utf-8")

    assert installer_module._install_claude(dry_run=False) == 1
    assert settings_path.read_text(encoding="utf-8") == "{not-json"


def test_claude_install_refuses_non_object_existing_json(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("[]", encoding="utf-8")

    assert installer_module._install_claude(dry_run=False) == 1
    assert settings_path.read_text(encoding="utf-8") == "[]"


def test_codex_install_refuses_invalid_existing_hooks_json(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(installer_module, "_find_binary", lambda: "vibeforcer")
    hooks_path = tmp_path / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text("{not-json", encoding="utf-8")

    assert installer_module._install_codex(dry_run=False) == 1
    assert hooks_path.read_text(encoding="utf-8") == "{not-json"


def test_codex_uninstall_refuses_non_object_existing_hooks_json(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    hooks_path = tmp_path / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text("[]", encoding="utf-8")

    assert installer_module._uninstall_codex(dry_run=False) == 1
    assert hooks_path.read_text(encoding="utf-8") == "[]"


def _codex_invalid_toml_install_paths(tmp_path: Path) -> tuple[Path, Path]:
    hooks_path = tmp_path / ".codex" / "hooks.json"
    config_path = tmp_path / ".codex" / "config.toml"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(json.dumps({"hooks": {}}), encoding="utf-8")
    config_path.write_text("broken = [\n", encoding="utf-8")
    return hooks_path, config_path


def test_codex_install_refuses_invalid_existing_config_toml_before_hooks_write(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    hooks_path, config_path = _codex_invalid_toml_install_paths(tmp_path)

    assert installer_module._install_codex(dry_run=False) == 1

    assert json.loads(hooks_path.read_text(encoding="utf-8")) == {"hooks": {}}
    assert config_path.read_text(encoding="utf-8") == "broken = [\n"


def _existing_claude_settings() -> dict[str, object]:
    return {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "other-gate"}]},
                {"hooks": [{"type": "command", "command": "/old/bin/vibeforcer handle"}]},
            ]
        }
    }


def _existing_codex_hooks() -> dict[str, object]:
    return {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "other-gate"}]},
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "/old/bin/vibeforcer handle --platform codex",
                        }
                    ],
                },
            ]
        }
    }


def _install_with_existing_hooks(
    tmp_path: Path,
    monkeypatch: Any,
    harness_dir: str,
    file_name: str,
    existing_hooks: dict[str, object],
) -> Path:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(installer_module, "_find_binary", lambda: "vibeforcer")
    hooks_path = tmp_path / harness_dir / file_name
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(json.dumps(existing_hooks), encoding="utf-8")
    return hooks_path


def _installed_hook_commands(hooks_path: Path) -> list[str]:
    return _hook_commands(json.loads(hooks_path.read_text(encoding="utf-8"))["hooks"])


