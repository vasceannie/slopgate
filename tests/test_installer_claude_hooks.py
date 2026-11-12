"""Claude hook rendering and existing Codex installer tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from hypothesis import given, strategies
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


def _wsl_hook_forward(monkeypatch: MonkeyPatch, inherited: str | None) -> set[str]:
    """``WSLENV|<user check>`` each WSL-hosted hook command hands its child."""

    def reporting_command(*_args: str, **_kwargs: str) -> str:
        return (
            "sh -c '"
            'test "$SLOPGATE_WSL_USER" = "$(id -un)" && user=session-user; '
            'printf "%s|%s" "$WSLENV" "${user:-other}"'
            "'"
        )

    monkeypatch.setattr("slopgate.installer._claude.hook_command", reporting_command)
    commands = set(
        all_hook_commands(
            object_dict(slopgate.installer.claude_hooks_block("x", wsl_hosted=True))
        )
    )
    env = {key: value for key, value in os.environ.items() if key != "WSLENV"}
    if inherited is not None:
        env["WSLENV"] = inherited
    return {
        subprocess.run(
            ["sh", "-c", command], env=env, capture_output=True, text=True, check=True
        ).stdout
        for command in commands
    }


@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX shell")
@pytest.mark.parametrize(
    ("inherited", "forwarded"),
    (
        (None, "WSL_DISTRO_NAME:SLOPGATE_WSL_USER"),
        ("TOKEN/p", "WSL_DISTRO_NAME:SLOPGATE_WSL_USER:TOKEN/p"),
    ),
    ids=("no-wslenv", "keeps-existing-wslenv"),
)
def test_wsl_hosted_hooks_forward_the_distribution_and_user_to_windows(
    monkeypatch: MonkeyPatch, inherited: str | None, forwarded: str
) -> None:
    assert _wsl_hook_forward(monkeypatch, inherited) == {f"{forwarded}|session-user"}, (
        "Claude inside WSL must hand its distribution and its own user to the "
        "Windows Slopgate so Linux paths resolve as the session that sent them"
    )


def _hosted_command_shape(binary: str, wsl_hosted: bool) -> set[tuple[bool, bool]]:
    """Per rendered command: (ends with the native command, prefix sets WSLENV)."""
    block = slopgate.installer.claude_hooks_block
    (native,) = set(all_hook_commands(object_dict(block(binary))))
    rendered = set(all_hook_commands(object_dict(block(binary, wsl_hosted=wsl_hosted))))
    return {
        (command.endswith(native), "WSLENV=" in command.removesuffix(native))
        for command in rendered
    }


@given(
    binary=strategies.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789/._-", min_size=1, max_size=24
    ),
    wsl_hosted=strategies.booleans(),
)
def test_claude_hooks_block_wsl_hosting_only_prefixes_the_shared_command_property(
    binary: str, wsl_hosted: bool
) -> None:
    assert _hosted_command_shape(binary, wsl_hosted) == {(True, wsl_hosted)}, (
        "every event shares one command; WSL hosting only prepends the WSLENV "
        "forward and never alters the Slopgate invocation itself"
    )


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
