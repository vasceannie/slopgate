"""Edge-case tests for Windows schtasks XML parsing.

Covers malformed XML, empty stdout, path normalization with forward/backslashes,
and non-zero exit handling.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence, cast

import pytest

from slopgate.installer._suite_autoupdate_windows import (
    path_appears_in_task_xml,
    query_windows_task_xml,
)


class TestQueryWindowsTaskXml:
    def test_returns_none_on_nonzero_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _fake_run_fail(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            assert "schtasks" in str(args), f"Expected schtasks in args: {args}"
            return subprocess.CompletedProcess(cast(Sequence[str], args), 1, stdout="")

        monkeypatch.setattr(subprocess, "run", _fake_run_fail)
        result = query_windows_task_xml()
        assert result is None, (
            f"Expected None when schtasks returns non-zero, got {result!r}"
        )

    def test_returns_stdout_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        xml = "<Task><Actions><Exec><Command>slopgate.exe</Command></Exec></Actions></Task>"

        def _fake_run_success(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            assert "schtasks" in str(args), f"Expected schtasks in args: {args}"
            return subprocess.CompletedProcess(cast(Sequence[str], args), 0, stdout=xml)

        monkeypatch.setattr(subprocess, "run", _fake_run_success)
        result = query_windows_task_xml()
        assert result == xml, (
            f"Expected XML stdout, got {result!r}"
        )


class TestPathAppearsInTaskXml:
    def test_empty_xml_returns_false(self) -> None:
        script = Path("C:\\slopgate.exe")
        assert not path_appears_in_task_xml(script, ""), (
            "Empty XML should never match any path"
        )

    def test_malformed_xml_returns_false(self) -> None:
        script = Path("slopgate.exe")
        assert not path_appears_in_task_xml(script, "<Malformed>"), (
            "Malformed XML should not crash and should not match"
        )

    def test_forward_slash_path_matches_backslash_xml(self) -> None:
        script = Path("C:/Program Files/Slopgate/update.ps1")
        xml = "<Task><Actions><Exec><Command>C:\\Program Files\\Slopgate\\update.ps1</Command></Exec></Actions></Task>"
        assert path_appears_in_task_xml(script, xml), (
            f"Expected forward-slash path to match backslash XML, script={script}"
        )

    def test_backslash_path_matches_forward_slash_xml(self) -> None:
        script = Path("C:\\Slopgate\\update.ps1")
        xml = "<Task><Actions><Exec><Command>C:/Slopgate/update.ps1</Command></Exec></Actions></Task>"
        assert path_appears_in_task_xml(script, xml), (
            f"Expected backslash path to match forward-slash XML, script={script}"
        )
