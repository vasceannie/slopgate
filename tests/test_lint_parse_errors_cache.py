"""Contracts for parse-error reuse of the request-local parse cache."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.lint._helpers.parsing import reset_request_analysis_cache
from slopgate.lint._parse_errors import detect_python_parse_errors


def _parse_error_cache_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    reset_request_analysis_cache()
    broken = tmp_path / "broken.py"
    broken.write_text("def broken(:\n", encoding="utf-8")
    first = detect_python_parse_errors([broken])

    def fail_read(self: Path, *args: object, **kwargs: object) -> str:
        raise AssertionError("detect_python_parse_errors reread after cache")

    monkeypatch.setattr(Path, "read_text", fail_read)
    second = detect_python_parse_errors([broken])
    return second[0].identifier if first and second else ""


def test_detect_python_parse_errors_reuses_request_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _parse_error_cache_contract(tmp_path, monkeypatch) == "line-1"


def test_detect_python_parse_errors_empty_paths() -> None:
    assert detect_python_parse_errors([]) == []
