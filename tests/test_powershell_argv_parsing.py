from __future__ import annotations

import pytest

from slopgate.installer._shared import _powershell_command_argv


class TestPowerShellCommandArgv:
    def test_parses_command_with_ampersand_prefix(self) -> None:
        argv = _powershell_command_argv(
            [
                "powershell.exe",
                "-Command",
                "& 'C:\\slopgate.exe' handle --platform claude",
            ]
        )
        assert argv == ["C:\\slopgate.exe", "handle", "--platform", "claude"], (
            f"Expected parsed argv with & stripped, got {argv}"
        )

    def test_parses_with_dash_c_alias(self) -> None:
        argv = _powershell_command_argv(
            ["powershell", "-c", "& 'slopgate.exe' handle"]
        )
        assert argv == ["slopgate.exe", "handle"], (
            f"Expected parsed argv with -c, got {argv}"
        )

    def test_returns_empty_list_when_no_command_flag(self) -> None:
        argv = _powershell_command_argv(
            ["powershell.exe", "-NoProfile", "-File", "script.ps1"]
        )
        assert argv == [], (
            f"Expected empty list when no -Command/-c flag, got {argv}"
        )

    def test_returns_args_without_ampersand(self) -> None:
        argv = _powershell_command_argv(
            ["powershell.exe", "-Command", "slopgate.exe handle"]
        )
        assert argv == ["slopgate.exe", "handle"], (
            f"Expected parsed argv without &, got {argv}"
        )

    def test_parses_path_with_spaces(self) -> None:
        argv = _powershell_command_argv(
            [
                "powershell.exe",
                "-Command",
                "& 'C:\\Program Files\\slopgate.exe' handle --platform cursor",
            ]
        )
        assert "C:\\Program Files\\slopgate.exe" in argv, (
            f"Expected program files path in argv, got {argv}"
        )
        assert "handle" in argv, f"Expected handle in argv, got {argv}"

    def test_returns_empty_list_for_malformed_shlex_input(self) -> None:
        argv = _powershell_command_argv(
            ["powershell.exe", "-Command", "'unclosed"]
        )
        assert argv == [], (
            f"Expected empty list for unclosed quote, got {argv}"
        )

    @pytest.mark.parametrize(
        "input_argv",
        [
            [],
            ["not_powershell.exe"],
            ["powershell.exe"],
        ],
    )
    def test_returns_empty_list_for_non_powershell_or_short_argv(
        self, input_argv: list[str]
    ) -> None:
        argv = _powershell_command_argv(input_argv)
        assert argv == [], (
            f"Expected empty list for input {input_argv}, got {argv}"
        )
