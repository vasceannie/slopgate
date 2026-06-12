from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, strategies

from slopgate.lint import ParsedFile, parse_file


def _fail_parse(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("parse_file reparsed an unchanged file")


@given(value=strategies.integers(min_value=-100, max_value=100))
def test_parse_file_round_trips_valid_python_files(value: int) -> None:
    with TemporaryDirectory() as directory:
        source = Path(directory) / "sample.py"
        source.write_text(f"VALUE = {value}\n", encoding="utf-8")
        parsed = parse_file(source)
    assert {
        "is_parsed_file": isinstance(parsed, ParsedFile),
        "path": parsed.path if parsed is not None else None,
        "lines": parsed.lines if parsed is not None else [],
    } == {
        "is_parsed_file": True,
        "path": source,
        "lines": [f"VALUE = {value}"],
    }


def test_parse_file_cache_reuses_unchanged_file() -> None:
    with TemporaryDirectory() as directory:
        source = Path(directory) / "cached.py"
        source.write_text("VALUE = 1\n", encoding="utf-8")
        first = parse_file(source)
        assert first is not None
        original_safe_parse = parse_file.__globals__["safe_parse"]
        parse_file.__globals__["safe_parse"] = _fail_parse
        try:
            assert parse_file(source) is first
        finally:
            parse_file.__globals__["safe_parse"] = original_safe_parse
        assert parse_file(source) is first


def test_parse_file_cache_refreshes_after_file_metadata_changes(tmp_path: Path) -> None:
    source = tmp_path / "cached.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    first = parse_file(source)
    assert first is not None
    source.write_text("VALUE = 1000\n", encoding="utf-8")
    second = parse_file(source)
    assert second is not None
    assert {
        "same_object": second is first,
        "lines": second.lines,
    } == {
        "same_object": False,
        "lines": ["VALUE = 1000"],
    }
