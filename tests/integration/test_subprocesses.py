from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.util import platform
from slopgate.util.platform import CREATE_NO_WINDOW
from slopgate.util.subprocesses import CommandResult, run_shell
from tests.support import SKIP_UNIX_ONLY

WIN32_CREATE_NO_WINDOW = 0x08000000


@SKIP_UNIX_ONLY
def test_run_shell_executes_command_from_requested_working_directory(
    tmp_path: Path,
) -> None:
    result = run_shell("pwd", tmp_path, timeout=5)

    assert result == CommandResult(
        command="pwd",
        cwd=str(tmp_path),
        returncode=0,
        stdout=f"{tmp_path}\n",
        stderr="",
    )


@pytest.mark.parametrize(
    ("windows", "expected"),
    [
        pytest.param(True, CREATE_NO_WINDOW, id="windows_suppresses_console"),
        pytest.param(False, 0, id="posix_contributes_no_flags"),
    ],
)
def test_child_creation_flags_follow_the_host_platform(
    monkeypatch: pytest.MonkeyPatch, windows: bool, expected: int
) -> None:
    monkeypatch.setattr(platform, "is_windows", lambda: windows)

    flags = platform.child_creation_flags()

    assert flags == expected, (
        "child spawn flags must suppress the console on Windows only; "
        f"is_windows()={windows} produced {flags:#x}"
    )


def test_create_no_window_matches_the_win32_contract() -> None:
    # https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags
    assert CREATE_NO_WINDOW == WIN32_CREATE_NO_WINDOW, (
        "CREATE_NO_WINDOW must stay equal to the Win32 flag value 0x08000000"
    )
