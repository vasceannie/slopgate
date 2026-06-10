from __future__ import annotations
import json
from collections.abc import Callable, Iterable
from pathlib import Path
import tomli
from pytest import CaptureFixture, MonkeyPatch
import slopgate.installer
import slopgate.installer._shared
from slopgate._types import (
    ObjectDict,
    is_object_dict,
    object_dict,
    object_list,
    string_value,
)

HookBlockBuilder = Callable[[str], ObjectDict]


def hook_builder(name: str) -> HookBlockBuilder:
    return getattr(slopgate.installer, name)


def _assert_canonical_codex_hooks_feature(config: ObjectDict) -> None:
    features = object_dict(config.get("features"))
    assert features.get("hooks") is True
    assert "codex_hooks" not in features


def dry_run_install_json(
    platform: str,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    *,
    binary: str | None = "slopgate",
    windows: bool = False,
) -> ObjectDict:

    def which(name: str) -> str | None:
        return binary if name == "slopgate" else None

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(slopgate.installer._shared, "is_windows", lambda: windows)
    monkeypatch.setattr(slopgate.installer._shared.shutil, "which", which)
    assert slopgate.installer.install_platform(platform, dry_run=True) == 0
    output = capsys.readouterr().out
    return object_dict(json.loads(output[output.index("{") :]))


def all_hook_commands(hooks: ObjectDict) -> Iterable[str]:
    for entries in hooks.values():
        for raw_entry in object_list(entries):
            if not is_object_dict(raw_entry):
                continue
            entry = raw_entry
            for raw_hook in object_list(entry.get("hooks")):
                if not is_object_dict(raw_hook):
                    continue
                command = string_value(raw_hook.get("command"))
                if command is not None:
                    yield command


def hook_commands(hooks: ObjectDict, event_name: str = "PreToolUse") -> list[str]:
    entries = object_list(hooks.get(event_name))
    commands: list[str] = []
    for raw_entry in entries:
        if not is_object_dict(raw_entry):
            continue
        entry = raw_entry
        for raw_hook in object_list(entry.get("hooks")):
            if not is_object_dict(raw_hook):
                continue
            command = string_value(raw_hook.get("command"))
            if command is not None:
                commands.append(command)
    return commands


def count_slopgate_hook_commands(commands: list[str], *fragments: str) -> int:
    return sum(
        1
        for command in commands
        if slopgate.installer._shared.command_is_slopgate_hook(command)
        and (not fragments or all(fragment in command for fragment in fragments))
    )


def expected_hook_command(binary: str, *args: str) -> str:
    return slopgate.installer._shared.hook_command(binary, *args)


def command_includes_slopgate_handle(command: str, *fragments: str) -> bool:
    return (
        slopgate.installer._shared.command_is_slopgate_hook(command)
        and all(fragment in command for fragment in fragments)
    )


def _hook_block_entry(hooks: ObjectDict, event_name: str) -> ObjectDict:
    entries = object_list(hooks.get(event_name))
    assert entries and is_object_dict(entries[0])
    return entries[0]


def _codex_hook_coverage_summary(hooks: ObjectDict) -> dict[str, object]:
    session_start = _hook_block_entry(hooks, "SessionStart")
    pre = _hook_block_entry(hooks, "PreToolUse")
    post = _hook_block_entry(hooks, "PostToolUse")
    permission = _hook_block_entry(hooks, "PermissionRequest")
    session_start_matcher = str(session_start.get("matcher", ""))
    pre_matcher = str(pre.get("matcher", ""))
    post_matcher = str(post.get("matcher", ""))
    permission_matcher = str(permission.get("matcher", ""))
    required_tools = {"Bash", "apply_patch", "Edit", "Write"}
    missing_tools_by_matcher = {
        "PreToolUse": sorted(
            (tool for tool in required_tools if tool not in pre_matcher)
        ),
        "PostToolUse": sorted(
            (tool for tool in required_tools if tool not in post_matcher)
        ),
        "PermissionRequest": sorted(
            (tool for tool in required_tools if tool not in permission_matcher)
        ),
    }
    return {
        "missing_tools_by_matcher": missing_tools_by_matcher,
        "session_sources_ok": all(
            (
                source in session_start_matcher
                for source in ("startup", "resume", "clear")
            )
        ),
    }


def _codex_install_artifact_summary(root: Path) -> dict[str, object]:
    hooks = object_dict(json.loads((root / ".codex" / "hooks.json").read_text()))
    config = tomli.loads((root / ".codex" / "config.toml").read_text())
    features = object_dict(config.get("features"))
    return {
        "has_permission_request": "PermissionRequest"
        in object_dict(hooks.get("hooks")),
        "hooks_feature": features.get("hooks"),
        "legacy_codex_hooks": "codex_hooks" in features,
    }


def test_codex_hooks_cover_current_tool_events() -> None:
    summary = _codex_hook_coverage_summary(
        hook_builder("codex_hooks_block")("slopgate")
    )
    assert summary == {
        "missing_tools_by_matcher": {
            "PreToolUse": [],
            "PostToolUse": [],
            "PermissionRequest": [],
        },
        "session_sources_ok": True,
    }


def test_codex_hooks_are_bash_only(
    capsys: CaptureFixture[str], monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    data = dry_run_install_json("codex", capsys, monkeypatch, tmp_path)
    hooks = object_dict(data.get("hooks"))
    commands = list(all_hook_commands(hooks))
    assert (
        bool(commands),
        all((command.startswith("slopgate ") for command in commands)),
        all((" handle" in command for command in commands)),
        all(("powershell.exe" not in command for command in commands)),
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
    slopgate.installer.enable_codex_hooks_toml(config_path)
    parsed = tomli.loads(config_path.read_text(encoding="utf-8"))
    _assert_canonical_codex_hooks_feature(parsed)
    assert parsed["features"]["plugin_hooks"] is True
    assert parsed["projects"]["/tmp/example"]["trust_level"] == "trusted"


def test_codex_installer_creates_toml_features_section(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    slopgate.installer.enable_codex_hooks_toml(config_path)
    parsed = tomli.loads(config_path.read_text(encoding="utf-8"))
    _assert_canonical_codex_hooks_feature(parsed)
    assert config_path.exists()


def test_codex_install_writes_hooks_and_toml_feature(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(slopgate.installer._shared, "find_binary", lambda: "slopgate")
    assert slopgate.installer.install_codex(dry_run=False) == 0
    assert _codex_install_artifact_summary(tmp_path) == {
        "has_permission_request": True,
        "hooks_feature": True,
        "legacy_codex_hooks": False,
    }


def test_claude_install_refuses_invalid_existing_json(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("{not-json", encoding="utf-8")
    assert slopgate.installer.install_claude(dry_run=False) == 1
    assert settings_path.read_text(encoding="utf-8") == "{not-json"


def test_claude_install_refuses_non_object_existing_json(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("[]", encoding="utf-8")
    assert slopgate.installer.install_claude(dry_run=False) == 1
    assert settings_path.read_text(encoding="utf-8") == "[]"


def test_codex_install_refuses_invalid_existing_hooks_json(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(slopgate.installer._shared, "find_binary", lambda: "slopgate")
    hooks_path = tmp_path / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text("{not-json", encoding="utf-8")
    assert slopgate.installer.install_codex(dry_run=False) == 1
    assert hooks_path.read_text(encoding="utf-8") == "{not-json"


def test_codex_uninstall_refuses_non_object_existing_hooks_json(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    hooks_path = tmp_path / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text("[]", encoding="utf-8")
    assert slopgate.installer.uninstall_codex(dry_run=False) == 1
    assert hooks_path.read_text(encoding="utf-8") == "[]"


def _codex_invalid_toml_install_paths(tmp_path: Path) -> tuple[Path, Path]:
    hooks_path = tmp_path / ".codex" / "hooks.json"
    config_path = tmp_path / ".codex" / "config.toml"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(json.dumps({"hooks": {}}), encoding="utf-8")
    config_path.write_text("broken = [\n", encoding="utf-8")
    return (hooks_path, config_path)


def test_codex_install_refuses_invalid_existing_config_toml_before_hooks_write(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    hooks_path, config_path = _codex_invalid_toml_install_paths(tmp_path)
    assert slopgate.installer.install_codex(dry_run=False) == 1
    assert json.loads(hooks_path.read_text(encoding="utf-8")) == {"hooks": {}}
    assert config_path.read_text(encoding="utf-8") == "broken = [\n"


def existing_claude_settings() -> ObjectDict:
    return {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "other-gate"}],
                },
                {"hooks": [{"type": "command", "command": "/old/bin/slopgate handle"}]},
            ]
        }
    }


def existing_codex_hooks() -> ObjectDict:
    return {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "other-gate"}],
                },
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "/old/bin/slopgate handle --platform codex",
                        }
                    ],
                },
            ]
        }
    }


def install_with_existing_hooks(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    harness_dir: str,
    file_name: str,
    existing_hooks: ObjectDict,
) -> Path:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(slopgate.installer._shared, "find_binary", lambda: "slopgate")
    hooks_path = tmp_path / harness_dir / file_name
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(json.dumps(existing_hooks), encoding="utf-8")
    return hooks_path


def installed_hook_commands(hooks_path: Path) -> list[str]:
    parsed = object_dict(json.loads(hooks_path.read_text(encoding="utf-8")))
    return hook_commands(object_dict(parsed.get("hooks")))
