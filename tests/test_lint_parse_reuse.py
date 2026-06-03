from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from vibeforcer.lint._detectors import code_smells
from vibeforcer.lint._detectors import logging_conventions
from vibeforcer.lint._detectors import stale_code
from vibeforcer.lint._detectors import wrappers
from vibeforcer.lint._detectors.test_smells import _basic_detection
from vibeforcer.lint import _helpers
from vibeforcer.lint._config import get_config
from vibeforcer.lint._helpers import (
    ParsedFile,
    build_parent_map,
    compute_string_line_ranges,
)


def _parsed(source: str, rel: str = "src/example.py") -> ParsedFile:
    tree = ast.parse(source)
    return ParsedFile(
        path=Path("/tmp/project") / rel,
        rel=rel,
        tree=tree,
        lines=source.splitlines(),
        parent_map=build_parent_map(tree),
        string_line_ranges=compute_string_line_ranges(tree),
    )


def _fail_parse(*_args: object, **_kwargs: object) -> ast.Module:
    raise AssertionError("detector reparsed a ParsedFile")


def _fail_read(*_args: object, **_kwargs: object) -> list[str]:
    raise AssertionError("detector reread a ParsedFile")


def _source_detector_results(parsed: ParsedFile) -> tuple[object, ...]:
    return (
        code_smells.detect_high_complexity([parsed]),
        code_smells.detect_long_methods([parsed]),
        code_smells.detect_too_many_params([parsed]),
        code_smells.detect_deep_nesting([parsed]),
        code_smells.detect_god_classes([parsed]),
        code_smells.detect_oversized_modules([parsed]),
        [violation.rule for violation in wrappers.detect_unnecessary_wrappers([parsed])],
    )


def test_source_detectors_reuse_parsed_files_without_reparsing(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = _parsed(
        "def wrapper(value):\n"
        "    return target(value)\n"
        "\n"
        "class Tiny:\n"
        "    def method(self):\n"
        "        return 1\n"
    )
    monkeypatch.setattr(_helpers, "safe_parse", _fail_parse)
    monkeypatch.setattr(_helpers, "read_lines", _fail_read)

    assert _source_detector_results(parsed) == ([], [], [], [], [], [], ["unnecessary-wrapper"])


def test_line_based_and_logging_detectors_reuse_parsed_files(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = _parsed(
        "import logging\n"
        "log = logging.getLogger(__name__)\n"
        "value: typing.List[str] = []\n"
    )
    cfg = replace(
        get_config(),
        deprecated_patterns=[(r"typing\.List", "use list[str]")],
        logger_function="make_logger",
        logging_infrastructure_path="",
        disallowed_logger_names={"log"},
        logger_variable="logger",
    )
    monkeypatch.setattr(stale_code, "get_config", lambda: cfg)
    monkeypatch.setattr(logging_conventions, "get_config", lambda: cfg)
    monkeypatch.setattr(_helpers, "safe_parse", _fail_parse)
    monkeypatch.setattr(_helpers, "read_lines", _fail_read)

    detector_rules = (
        [v.rule for v in stale_code.detect_stale_patterns([parsed])],
        [v.rule for v in logging_conventions.detect_direct_get_logger([parsed])],
        [v.rule for v in logging_conventions.detect_wrong_logger_name([parsed])],
    )
    assert detector_rules == (
        ["deprecated-pattern"],
        ["direct-get-logger"],
        ["wrong-logger-name"],
    )


def test_basic_test_detectors_reuse_parsed_files_without_reparsing(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = _parsed(
        "def test_no_assertion():\n"
        "    exercise()\n"
        "\n"
        "def test_ok():\n"
        "    assert 1 == 1\n",
        rel="tests/test_example.py",
    )
    monkeypatch.setattr(_helpers, "safe_parse", _fail_parse)

    detector_results = (
        _basic_detection.detect_long_tests([parsed]),
        _basic_detection.detect_eager_tests([parsed]),
        [v.rule for v in _basic_detection.detect_assertion_free_tests([parsed])],
    )
    assert detector_results == ([], [], ["assertion-free-test"])
