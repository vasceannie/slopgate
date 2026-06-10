from __future__ import annotations

from pathlib import Path

from slopgate.installer._suite_autoupdate_windows import path_appears_in_task_xml


class TestPathAppearsInTaskXml:
    def test_finds_path_in_valid_xml(self) -> None:
        xml = "<Task><Actions><Exec><Command>C:\\tools\\slopgate.exe</Command></Exec></Actions></Task>"
        result = path_appears_in_task_xml(Path("C:\\tools\\slopgate.exe"), xml)
        assert result is True, (
            f"Expected True for path present in valid XML, got {result}"
        )

    def test_returns_false_when_path_absent(self) -> None:
        xml = "<Task><Actions><Exec><Command>not-slopgate.exe</Command></Exec></Actions></Task>"
        result = path_appears_in_task_xml(Path("C:\\slopgate.exe"), xml)
        assert result is False, (
            f"Expected False for path not in XML, got {result}"
        )

    def test_handles_empty_xml_string(self) -> None:
        result = path_appears_in_task_xml(Path("C:\\slopgate.exe"), "")
        assert result is False, (
            f"Expected False for empty XML, got {result}"
        )

    def test_handles_malformed_xml(self) -> None:
        result = path_appears_in_task_xml(Path("C:\\slopgate.exe"), "<unclosed><tag>")
        assert result is False, (
            f"Expected False for malformed XML, got {result}"
        )

    def test_case_insensitive_path_matching(self) -> None:
        xml = "<Task><Exec><Command>C:\\Tools\\Slopgate.exe</Command></Exec></Task>"
        result = path_appears_in_task_xml(Path("c:\\tools\\slopgate.exe"), xml)
        assert result is True, (
            f"Expected True for case-insensitive path match, got {result}"
        )

    def test_forward_slash_path_matches_backslash_in_xml(self) -> None:
        xml = "<Task><Exec><Command>C:\\tools\\slopgate.exe</Command></Exec></Task>"
        result = path_appears_in_task_xml(Path("C:/tools/slopgate.exe"), xml)
        assert result is True, (
            f"Expected True when forward-slash path matches backslash XML, got {result}"
        )

    def test_backward_slash_path_matches_forward_slash_in_xml(self) -> None:
        xml = "<Task><Exec><Command>C:/tools/slopgate.exe</Command></Exec></Task>"
        result = path_appears_in_task_xml(Path("C:\\tools\\slopgate.exe"), xml)
        assert result is True, (
            f"Expected True when backslash path matches forward-slash XML, got {result}"
        )
