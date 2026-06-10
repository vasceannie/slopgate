from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
from hypothesis import given, strategies
from slopgate.lint._config import load_config, reset_config, set_config
from slopgate.lint._detectors.duplicates import detect_repeated_literals
from slopgate.lint._helpers import ParsedFile, ensure_parsed, parse_files
from slopgate.lint._parse_errors import detect_python_parse_errors


@given(value=strategies.integers(min_value=-100, max_value=100))
def test_lint_parse_pipeline_round_trips_valid_python_files(value: int) -> None:
    with TemporaryDirectory() as directory:
        source = Path(directory) / "sample.py"
        source.write_text(f"VALUE = {value}\n", encoding="utf-8")
        parsed = parse_files([source])
        ensured = ensure_parsed(parsed)
    assert {
        "parsed_count": len(parsed),
        "ensured_count": len(ensured),
        "same_path": ensured[0].path == source,
        "is_parsed_file": isinstance(ensured[0], ParsedFile),
    } == {
        "parsed_count": 1,
        "ensured_count": 1,
        "same_path": True,
        "is_parsed_file": True,
    }


def test_lint_parse_pipeline_skips_invalid_python_files(tmp_path: Path) -> None:
    valid = tmp_path / "valid.py"
    invalid = tmp_path / "invalid.py"
    valid.write_text("ANSWER = 42\n", encoding="utf-8")
    invalid.write_text("def broken(:\n", encoding="utf-8")
    assert [item.path for item in ensure_parsed(None, fallback=[valid, invalid])] == [
        valid
    ]


def test_lint_parse_pipeline_reports_parse_error_locations(tmp_path: Path) -> None:
    valid = tmp_path / "valid.py"
    invalid = tmp_path / "invalid.py"
    valid.write_text("ANSWER = 42\n", encoding="utf-8")
    invalid.write_text("def broken(:\n", encoding="utf-8")
    violations = detect_python_parse_errors([valid, invalid])
    assert [(item.rule, item.relative_path, item.metadata) for item in violations] == [
        ("python-parse-error", str(invalid), {"line": 1, "offset": 12})
    ]


def _repeated_literal_violation_for(literal: str) -> dict[str, object]:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        _ = (root / "src").mkdir()
        cfg = load_config(root)
        set_config(cfg)
        try:
            sources: list[Path] = []
            for index in range(11):
                source = root / "src" / f"case_{index}.py"
                source.write_text(f"VALUE = {literal!r}\n", encoding="utf-8")
                sources.append(source)
            parsed = parse_files(sources)
            violations = detect_repeated_literals(parsed)
        finally:
            reset_config()
    repeated = [item for item in violations if item.rule == "repeated-string-literal"]
    return {
        "violation_count": len(repeated),
        "has_candidate": bool(repeated[0].metadata["candidate_constant_name"]),
    }


@given(literal=strategies.from_regex("LaneC[A-Za-z0-9_]{1,12}", fullmatch=True))
def test_lint_parse_pipeline_property_checks_repeated_literal_semantics(
    literal: str,
) -> None:
    assert _repeated_literal_violation_for(literal) == {
        "violation_count": 1,
        "has_candidate": True,
    }
