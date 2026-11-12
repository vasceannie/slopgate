"""A WSL-hosted Claude CLI reports Linux paths the Windows installer must compare."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, strategies

from slopgate.constants import INSTALL_SCOPE_PROJECT
from slopgate.installer.native.claude import ClaudeHost, ClaudeLayout
from slopgate.installer.native.commands import NativeCommandError
from slopgate.installer.native.wsl import WslPaths, read_wsl_shim
from tests.native.wsl_support import (
    WSL_HOME_UNC,
    install_failing_wsl,
    install_wsl_commands,
)


@pytest.mark.parametrize(
    ("reported", "expected"),
    (
        ("/mnt/c/Users/PC/x", "C:\\Users\\PC\\x"),
        ("/home/trav/.claude", WSL_HOME_UNC),
        ("C:\\Users\\PC\\x", "C:\\Users\\PC\\x"),
        ("<missing marketplace path>", "<missing marketplace path>"),
    ),
    ids=("drive-mount", "wsl-home", "already-windows", "placeholder-text"),
)
def test_to_windows_translates_only_wsl_absolute_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reported: str,
    expected: str,
) -> None:
    install_wsl_commands(tmp_path, monkeypatch)

    translated = WslPaths(tmp_path).to_windows(reported)

    assert str(translated) == expected, (
        "WSL-absolute paths must map through wslpath; other text passes through"
    )


def test_claude_config_dir_is_opened_through_the_wsl_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_wsl_commands(tmp_path, monkeypatch)

    config_dir = WslPaths(tmp_path).claude_config_dir()

    assert str(config_dir) == WSL_HOME_UNC, (
        "user settings live in the WSL home, which Windows reaches by UNC path"
    )


def test_failed_wslpath_surfaces_as_native_command_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_failing_wsl(tmp_path, monkeypatch)

    with pytest.raises(NativeCommandError, match="exited 3"):
        WslPaths(tmp_path).to_windows("/mnt/c/x")


def test_shim_target_routes_every_bridge_call_to_its_distribution_and_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_wsl_commands(tmp_path, monkeypatch)
    bridge = WslPaths(tmp_path, ("-d", "Debian", "-u", "ops"))

    observed = (str(bridge.to_windows("/home/ops/x")), str(bridge.claude_config_dir()))

    assert observed == (
        "\\\\wsl.localhost\\Debian\\home\\ops\\x",
        "\\\\wsl.localhost\\Debian\\home\\ops\\.claude",
    ), "path and config lookups must reach the shim's distribution and user"


@pytest.mark.parametrize(
    ("command_line", "target"),
    (
        ("wsl claude %*", ()),
        ("wsl -e claude %*", ()),
        ("wsl -d Ubuntu-22.04 claude %*", ("-d", "Ubuntu-22.04")),
        (
            '"C:\\Windows\\System32\\wsl.exe" --distribution "Debian" -e claude %*',
            ("--distribution", "Debian"),
        ),
        ("wsl -u trav -d claude-dev claude %*", ("-u", "trav", "-d", "claude-dev")),
        ("wsl ~ --cd /tmp -d Arch claude %*", ("-d", "Arch")),
        ("wsl -e claude -d NotWsl %*", ()),
        ('wsl -d "Ubuntu 22.04" claude %*', ("-d", "Ubuntu 22.04")),
        (
            'wsl -u "my user" -d Ub"untu 2"2 claude %*',
            ("-u", "my user", "-d", "Ubuntu 22"),
        ),
        (
            '@call "C:\\Program Files\\WSL\\wsl.exe" -d Ubuntu claude %*',
            ("-d", "Ubuntu"),
        ),
    ),
    ids=(
        "default",
        "exec-only",
        "short-flag",
        "long-flag-quoted",
        "user-and-distro-named-like-command",
        "home-and-cd-skipped",
        "command-argument-not-wsl-option",
        "quoted-value-with-space",
        "quotes-group-mid-argument",
        "quoted-executable-path-with-spaces",
    ),
)
def test_shim_target_keeps_only_the_options_that_pick_distribution_and_user(
    tmp_path: Path, command_line: str, target: tuple[str, ...]
) -> None:
    script = tmp_path / "claude.bat"
    script.write_text(f"@echo off\r\n{command_line}\r\n", encoding="utf-8")

    shim = read_wsl_shim(script)

    assert shim is not None and shim.target == target, (
        "every wsl option selecting where claude runs must reach the bridge calls"
    )


@pytest.mark.parametrize(
    ("name", "content", "expected"),
    (
        ("claude.bat", "@echo off\r\nwsl claude %*\r\n", True),
        ("claude.cmd", "@echo off\r\nC:\\Windows\\System32\\wsl.exe claude %*", True),
        (
            "claude.bat",
            '@echo off\r\n@call "C:\\Windows\\System32\\wsl.exe" -e claude %*',
            True,
        ),
        ("claude.bat", '@echo off\r\n"C:\\Tools\\claude.exe" %*\r\n', False),
        (
            "claude.bat",
            '@echo off\r\n"C:\\Program Files\\notwsl.exe" claude %*\r\n',
            False,
        ),
        (
            "claude.bat",
            '@echo off\r\nREM wsl claude is the old way\r\n"C:\\Tools\\claude.exe" %*',
            False,
        ),
        (
            "claude.bat",
            '@echo off\r\necho wsl claude moved\r\n"C:\\Tools\\claude.exe" %*',
            False,
        ),
        (
            "claude.bat",
            "@echo off\r\nif exist C:\\Tools\\claude.exe (C:\\Tools\\claude.exe %*) else wsl claude %*",
            False,
        ),
        ("claude.bat", "@echo off\r\nwsl ls %*\r\n", False),
        ("claude.ps1", "wsl claude @args", False),
    ),
    ids=(
        "bat-wsl",
        "cmd-wsl-exe",
        "call-wsl-exe-with-e",
        "bat-native",
        "quoted-path-to-other-executable",
        "rem-comment",
        "echo-message",
        "conditional-wrapper",
        "wsl-runs-other-command",
        "ps1-not-shim",
    ),
)
def test_wsl_shim_detection_reads_the_forwarding_batch_file(
    tmp_path: Path, name: str, content: str, expected: bool
) -> None:
    script = tmp_path / name
    script.write_bytes(content.encode())

    assert (read_wsl_shim(script) is not None) is expected, (
        "only a .bat/.cmd whose command line runs wsl <name> is a WSL shim"
    )


def test_wsl_host_compares_windows_paths_for_sources_and_project_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_wsl_commands(tmp_path, monkeypatch)
    layout = ClaudeLayout(
        user_settings=lambda: tmp_path / "settings.json",
        project_settings=lambda root: root / ".claude" / "settings.json",
        user_root=lambda: tmp_path,
        render_payload=lambda binary, version: {"v": json.dumps([binary, version])},
    )
    host = ClaudeHost(layout, WslPaths(tmp_path))

    sources = host.marketplace_sources(tmp_path)
    registrations = host.registrations(tmp_path)

    assert sources == {
        "slopgate-runtime": (
            "C:\\Users\\PC\\AppData\\Local\\slopgate\\native\\claude\\marketplace"
        )
    }, "the marketplace source must come back in the installer's Windows form"
    assert [(item.scope, str(item.project)) for item in registrations] == [
        (INSTALL_SCOPE_PROJECT, "C:\\Users\\PC\\project")
    ], "a project registration must carry the Windows project path"


def _shim_verdict(suffix: str, body: str) -> bool:
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory, f"claude{suffix}")
        script.write_text(body, encoding="utf-8")
        return read_wsl_shim(script) is not None


@given(
    prefix=strategies.text(
        alphabet=strategies.characters(blacklist_categories=("Cs",)), max_size=30
    ),
    suffix=strategies.sampled_from((".bat", ".cmd", ".BAT", ".exe", ".ps1", "")),
)
def test_shim_requires_a_batch_suffix_and_a_wsl_word(prefix: str, suffix: str) -> None:
    verdict = _shim_verdict(suffix, f"{prefix}\nwsl claude %*\n")

    assert verdict is (suffix.lower() in {".bat", ".cmd"}), (
        "a WSL invocation only makes a shim when the file is a batch script"
    )
