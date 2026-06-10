from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.installer._suite_autoupdate_windows import path_appears_in_task_xml


class TestPathAppearsInTaskXml:
    @pytest.mark.parametrize(
        "xml, path",
        [
            (
                "<Task><Actions><Exec><Command>C:\\tools\\slopgate.exe</Command></Exec></Actions></Task>",
                "C:\\tools\\slopgate.exe",
            ),
            (
                "<Task><Exec><Command>C:\\Tools\\Slopgate.exe</Command></Exec></Task>",
                "c:\\tools\\slopgate.exe",
            ),
            (
                "<Task><Exec><Command>C:\\tools\\slopgate.exe</Command></Exec></Task>",
                "C:/tools/slopgate.exe",
            ),
            (
                "<Task><Exec><Command>C:/tools\\slopgate.exe</Command></Exec></Task>",
                "C:\\tools\\slopgate.exe",
            ),
        ],
    )
    def test_detects_path_match(self, xml: str, path: str) -> None:
        assert path_appears_in_task_xml(Path(path), xml)

    def test_returns_false_when_path_absent(self) -> None:
        xml = "<Task><Actions><Exec><Command>not-slopgate.exe</Command></Exec></Actions></Task>"
        result = path_appears_in_task_xml(Path("C:\\slopgate.exe"), xml)
        assert result is False, f"Expected False for path not in XML, got {result}"

    def test_handles_empty_xml_string(self) -> None:
        result = path_appears_in_task_xml(Path("C:\\slopgate.exe"), "")
        assert result is False, f"Expected False for empty XML, got {result}"

    def test_handles_malformed_xml(self) -> None:
        result = path_appears_in_task_xml(Path("C:\\slopgate.exe"), "<unclosed><tag>")
        assert result is False, f"Expected False for malformed XML, got {result}"
