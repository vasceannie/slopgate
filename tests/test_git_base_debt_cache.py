from __future__ import annotations

import subprocess

from slopgate.cli.lint.git_base_debt import _finish_git_archive_process


class _TimeoutThenExitProcess:
    def __init__(self, exit_code: int) -> None:
        self._exit_code = exit_code
        self.killed = False
        self.wait_calls = 0

    def wait(self, timeout: int) -> int:
        del timeout
        self.wait_calls += 1
        if self.wait_calls == 1:
            raise subprocess.TimeoutExpired("git archive", timeout=1)
        return self._exit_code

    def kill(self) -> None:
        self.killed = True


def test_finish_git_archive_process_kills_and_waits_after_timeout() -> None:
    process = _TimeoutThenExitProcess(exit_code=0)

    finished = _finish_git_archive_process(process)

    assert {
        "finished": finished,
        "killed": process.killed,
        "wait_calls": process.wait_calls,
    } == {
        "finished": True,
        "killed": True,
        "wait_calls": 2,
    }
