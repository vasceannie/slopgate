"""Claude hook rendering and existing Codex installer tests."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from pytest import CaptureFixture, MonkeyPatch
from slopgate._types import ObjectDict, object_dict
from slopgate.constants import PLATFORM_CLAUDE
import slopgate.installer
from tests.test_installer import (
    InstallDryRunCase,
    all_hook_commands,
    command_includes_slopgate_handle,
    dry_run_install_json,
    existing_codex_hooks,
    installed_hook_commands,
)
from tests.native.commands import unquoted_command


@dataclass(frozen=True, slots=True)
class ExistingHooksCase:
    harness_dir: str
    file_name: str
    existing_hooks: ObjectDict


def install_with_existing_hooks(
    tmp_path: Path, monkeypatch: MonkeyPatch, case: ExistingHooksCase
) -> Path:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    hooks_path = tmp_path / case.harness_dir / case.file_name
    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    hooks_path.write_text(json.dumps(case.existing_hooks), encoding="utf-8")
    return hooks_path


def test_claude_hooks_include_cwd_changed_and_explicit_platform() -> None:
    hooks = object_dict(slopgate.installer.claude_hooks_block("slopgate"))
    assert "CwdChanged" in hooks, "Claude hook definitions must retain CwdChanged"
    commands = list(all_hook_commands(hooks))
    assert commands, "Claude hook block should render hook commands"
    assert all(
        f"--platform {PLATFORM_CLAUDE}" in unquoted_command(command)
        for command in commands
    ), "Claude-installed hooks must identify their platform explicitly"


def test_claude_python_fallback_uses_module_invocation() -> None:
    commands = list(
        all_hook_commands(
            object_dict(slopgate.installer.claude_hooks_block(sys.executable))
        )
    )
    assert commands, "Claude hook block must contain command invocations"
    assert all(
        " -m slopgate handle" in unquoted_command(command) for command in commands
    ), "Python fallback should invoke Slopgate as a module"
    assert all(
        f"--platform {PLATFORM_CLAUDE}" in unquoted_command(command)
        for command in commands
    ), "Python fallback must identify the Claude platform"


def test_codex_install_preserves_unrelated_hooks_and_replaces_only_slopgate(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    hooks_path = install_with_existing_hooks(
        tmp_path,
        monkeypatch,
        ExistingHooksCase(".codex", "hooks.json", existing_codex_hooks()),
    )
    assert slopgate.installer.install_codex(dry_run=False) == 0
    commands = installed_hook_commands(hooks_path)
    assert "other-gate" in commands
    assert "/old/bin/slopgate handle --platform codex" not in commands
    assert (
        sum(
            command_includes_slopgate_handle(command, "--platform", "codex")
            for command in commands
        )
        == 1
    )


def test_codex_uninstall_preserves_non_hook_user_settings_when_only_owned_hooks_remain(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    hooks_path = tmp_path / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(
        json.dumps(
            {
                "customSetting": {"keep": True},
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "slopgate handle --platform codex",
                                }
                            ],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    assert slopgate.installer.uninstall_codex(dry_run=False) == 0
    remaining = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert remaining == {"customSetting": {"keep": True}}, (
        "Codex uninstall must preserve non-hook settings"
    )
    assert sorted(hooks_path.parent.glob("hooks.json.slopgate-bak-*")), (
        "Codex uninstall must keep a backup"
    )


def test_windows_codex_install_emits_powershell_hook_commands(
    capsys: CaptureFixture[str], monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    data = dry_run_install_json(
        InstallDryRunCase(
            platform="codex",
            binary="C:\\Users\\Trav App\\AppData\\Local\\Programs\\Python\\Scripts\\slopgate.exe",
            windows=True,
        ),
        capsys,
        monkeypatch,
        tmp_path,
    )
    commands = list(all_hook_commands(object_dict(data["hooks"])))
    assert commands, "Codex dry-run should render PowerShell hook commands"
    contracts = [
        command.startswith("powershell.exe ")
        and "-NoProfile" in command
        and "-NonInteractive" in command
        and "-Command" in command
        and "C:\\Users\\Trav App\\AppData" in command
        and "handle" in command
        and "codex" in command
        for command in commands
    ]
    assert contracts == [True] * len(commands), (
        "Codex command rendering must preserve its PowerShell contract"
    )
