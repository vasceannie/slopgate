from __future__ import annotations

from slopgate.installer._shared import hook_command, shell_command


class TestShellCommand:
    def test_posix_uses_shlex_join(self) -> None:
        result = shell_command(
            ["slopgate", "handle", "--platform", "claude"], windows=False
        )
        assert "slopgate" in result, f"Expected slopgate in command, got {result}"
        assert "powershell" not in result.lower(), (
            f"Expected no powershell on posix, got {result}"
        )

    def test_windows_wraps_with_powershell(self) -> None:
        result = shell_command(
            ["C:\\Tools\\slopgate.exe", "handle"], windows=True
        )
        assert result.startswith("powershell.exe"), (
            f"Expected powershell.exe wrapper, got {result}"
        )
        assert "-NoProfile" in result, f"Expected -NoProfile flag, got {result}"

    def test_windows_path_with_spaces(self) -> None:
        result = shell_command(
            ["C:\\Program Files\\Slopgate\\slopgate.exe", "handle"],
            windows=True,
        )
        assert "'C:\\Program Files\\Slopgate\\slopgate.exe'" in result, (
            f"Expected path with spaces to be single-quote wrapped, got {result}"
        )

    def test_windows_path_with_apostrophe(self) -> None:
        result = shell_command(
            ["C:\\O'Brien's Tools\\slopgate.exe", "handle"], windows=True
        )
        assert "O''Brien''s" in result, (
            f"Expected apostrophe to be PowerShell-escaped (''), got {result}"
        )

    def test_windows_path_with_spaces_and_apostrophes(self) -> None:
        result = shell_command(
            ["C:\\Program Files\\O'Brien's Tools\\slopgate.exe", "handle"],
            windows=True,
        )
        assert "'C:\\Program Files\\O''Brien''s Tools\\slopgate.exe'" in result, (
            f"Expected path with spaces+apostrophes wrapped+escaped, got {result}"
        )

    def test_windows_empty_args(self) -> None:
        result = shell_command([], windows=True)
        assert result.startswith("powershell.exe"), (
            f"Expected powershell wrapper even with empty args, got {result}"
        )


class TestHookCommand:
    def test_posix(self) -> None:
        result = hook_command(
            "/usr/local/bin/slopgate", "handle", windows=False,
        )
        assert "/usr/local/bin/slopgate" in result, (
            f"Expected binary path in command, got {result}"
        )
        assert "powershell" not in result.lower(), (
            f"Expected no powershell wrapping on posix, got {result}"
        )

    def test_windows_spaces(self) -> None:
        result = hook_command(
            "C:\\Program Files\\Slopgate\\slopgate.exe", "handle",
            windows=True,
        )
        assert "powershell.exe" in result, (
            f"Expected powershell wrapper on windows, got {result}"
        )
        assert "Program Files" in result, (
            f"Expected Program Files path preserved, got {result}"
        )
