"""Sandbox helpers shared by Claude native-installer tests."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pytest import MonkeyPatch

import slopgate.installer._shared
from slopgate._types import object_dict, object_list
from slopgate.installer.native.migration import extract_owned_hooks
from slopgate.installer.native.packages import native_host_root
from tests.native.claude_fake import write_fake_claude
from tests.native.environment import isolate_native_data_dirs


@dataclass(frozen=True, slots=True)
class ClaudeHarness:
    home: Path
    project: Path
    fake_bin: Path
    state_path: Path
    log_path: Path

    @property
    def user_settings(self) -> Path:
        return self.home / ".claude" / "settings.json"

    @property
    def project_settings(self) -> Path:
        return self.project / ".claude" / "settings.json"

    @property
    def staging_root(self) -> Path:
        return native_host_root("claude")


def claude_harness(tmp_path: Path, monkeypatch: MonkeyPatch) -> ClaudeHarness:
    isolate_native_data_dirs(monkeypatch, tmp_path)
    home = tmp_path / "home"
    project = tmp_path / "project with spaces"
    fake_bin = tmp_path / "fake-bin"
    home.mkdir()
    project.mkdir()
    write_fake_claude(fake_bin)
    state_path = tmp_path / "fake-state.json"
    log_path = tmp_path / "fake-calls.jsonl"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    monkeypatch.setattr(slopgate.installer._shared, "find_binary", lambda: "slopgate")
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("FAKE_CLAUDE_STATE", str(state_path))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log_path))
    monkeypatch.delenv("FAKE_CLAUDE_FAIL", raising=False)
    monkeypatch.delenv("FAKE_CLAUDE_FAIL_AFTER", raising=False)
    return ClaudeHarness(home, project, fake_bin, state_path, log_path)


def legacy_settings() -> dict[str, object]:
    return {
        "customSetting": {"keep": True},
        "enabledPlugins": {"unrelated-plugin@other-market": True},
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "legacyGroup": "preserve-on-rollback",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "slopgate handle --platform claude",
                        },
                        {"type": "command", "command": "other-gate"},
                    ],
                }
            ],
            "Stop": [
                {"hooks": [{"type": "command", "command": "unrelated-stop-hook"}]}
            ],
        },
    }


def seed_legacy_settings(
    harness: ClaudeHarness,
) -> tuple[dict[str, object], dict[str, object]]:
    user = legacy_settings()
    project = legacy_settings()
    for path, document in (
        (harness.user_settings, user),
        (harness.project_settings, project),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return user, project


def settings_document(path: Path) -> dict[str, object]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a settings object at {path}")
    return cast(dict[str, object], parsed)


def fake_state(harness: ClaudeHarness) -> dict[str, object]:
    if not harness.state_path.exists():
        return {"marketplaces": {}, "plugins": []}
    return settings_document(harness.state_path)


def fake_calls(harness: ClaudeHarness) -> list[list[str]]:
    if not harness.log_path.exists():
        return []
    lines = harness.log_path.read_text(encoding="utf-8").splitlines()
    return [cast(list[str], json.loads(line)) for line in lines]


def mutating_calls(calls: list[list[str]]) -> list[list[str]]:
    mutations = {"add", "update", "remove", "install", "uninstall", "disable", "enable"}
    return [
        call
        for call in calls
        if len(call) > 1
        and (
            (call[1] == "marketplace" and len(call) > 2 and call[2] in mutations)
            or call[1] in mutations
        )
    ]


def tree_digest(roots: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for root in roots:
        digest.update(str(root).encode())
        digest.update(b"exists" if root.exists() else b"absent")
        if root.exists():
            for path in sorted(root.rglob("*")):
                digest.update(str(path.relative_to(root)).encode())
                if path.is_file():
                    digest.update(path.read_bytes())
    return digest.hexdigest()


def assert_legacy_removed(path: Path, original: dict[str, object]) -> None:
    current = settings_document(path)
    assert not extract_owned_hooks(current.get("hooks")), (
        "native install must retire legacy owned hooks"
    )
    assert current.get("customSetting") == original["customSetting"], (
        "unrelated settings must survive"
    )
    current_enabled = object_dict(current.get("enabledPlugins"))
    original_enabled = object_dict(original.get("enabledPlugins"))
    assert all(
        current_enabled.get(key) == value for key, value in original_enabled.items()
    ), "native changes must preserve unrelated enabledPlugins entries"
    hooks = object_dict(current.get("hooks"))
    entries = object_list(hooks.get("PreToolUse"))
    commands = [
        command
        for entry in entries
        for hook in object_list(object_dict(entry).get("hooks"))
        if isinstance((command := object_dict(hook).get("command")), str)
    ]
    assert commands == ["other-gate"], "mixed user hook commands must remain"


def assert_settings_rollback_preserved(path: Path, original: dict[str, object]) -> None:
    current = settings_document(path)
    assert current.get("hooks") == original.get("hooks"), (
        "rollback must restore original hook definitions"
    )
    assert current.get("customSetting") == original.get("customSetting"), (
        "rollback must preserve unrelated settings"
    )
    current_enabled = object_dict(current.get("enabledPlugins"))
    original_enabled = object_dict(original.get("enabledPlugins"))
    assert all(
        current_enabled.get(key) == value for key, value in original_enabled.items()
    ), "rollback must preserve unrelated enabledPlugins entries"


def catalog_plugin(catalog_path: Path) -> tuple[dict[str, object], Path]:
    catalog = settings_document(catalog_path)
    entries = object_list(catalog.get("plugins"))
    if not entries:
        raise AssertionError("Claude catalog must contain the enforcement plugin")
    entry = object_dict(entries[0])
    source = entry.get("source")
    if not isinstance(source, str):
        raise AssertionError("Claude catalog plugin source must be relative text")
    package_root = catalog_path.parent.parent / source.removeprefix("./")
    return entry, package_root


def seed_hook_settings(
    harness: ClaudeHarness, first_command: str, second_command: str
) -> Path:
    settings_path = harness.user_settings
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "unrelatedSetting": True,
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": first_command},
                        {"type": "command", "command": second_command},
                    ],
                }
            ]
        },
    }
    settings_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return settings_path
