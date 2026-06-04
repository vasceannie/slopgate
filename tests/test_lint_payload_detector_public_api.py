from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, strategies

from slopgate.lint._detectors.test_smells import (
    detect_hand_built_test_payloads,
    detect_mock_theater,
    detect_mocked_integration_tests,
    detect_schema_bypasses,
    detect_weak_assertions,
)
from slopgate.lint._helpers import ParsedFile, parse_files

IDENTIFIERS = strategies.from_regex(r"[a-z][a-z_]{0,12}", fullmatch=True)


def parsed_file(tmp_path: Path, source: str, name: str) -> list[ParsedFile]:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return parse_files([path])


def parsed_temp_source(source: str, name: str) -> list[ParsedFile]:
    with TemporaryDirectory() as raw_path:
        return parsed_file(Path(raw_path), source, name)


def test_payload_detector_reports_large_inline_payload_dict(tmp_path: Path) -> None:
    parsed = parsed_file(
        tmp_path,
        """
def test_request_builder() -> None:
    payload = {
        "a": 1,
        "b": 2,
        "c": 3,
        "d": 4,
        "e": 5,
        "f": 6,
        "g": 7,
        "h": 8,
    }
    assert payload["a"] == 1
""".lstrip(),
        "test_payloads.py",
    )

    violations = detect_hand_built_test_payloads(parsed)

    assert [(item.rule, item.identifier) for item in violations] == [
        ("hand-built-test-payload", "test_request_builder:line-2")
    ]


def test_payload_detector_reports_call_only_mock_assertions(tmp_path: Path) -> None:
    parsed = parsed_file(
        tmp_path,
        """
from unittest.mock import Mock

def test_mock_only_proof() -> None:
    handler = Mock()
    handler("value")
    handler.assert_called_once()
""".lstrip(),
        "test_mock.py",
    )

    violations = detect_mock_theater(parsed)

    assert [(item.rule, item.identifier) for item in violations] == [
        ("mock-theater", "test_mock_only_proof")
    ]


def test_payload_detector_reports_mocked_integration_tests(tmp_path: Path) -> None:
    parsed = parsed_file(
        tmp_path,
        """
from unittest.mock import patch

def test_pipeline_flow_integration() -> None:
    with patch("service.Client") as client:
        client.return_value.run.return_value = "ok"
        assert client.return_value.run() == "ok"
""".lstrip(),
        "tests/integration/test_pipeline.py",
    )

    violations = detect_mocked_integration_tests(parsed)

    assert [(item.rule, item.identifier) for item in violations] == [
        ("mocked-integration-test", "test_pipeline_flow_integration")
    ]


def test_payload_detector_reports_schema_bypass_casts(tmp_path: Path) -> None:
    parsed = parsed_file(
        tmp_path,
        """
from typing import cast

class HookState:
    pass

def test_payload_bypass() -> None:
    payload = cast(HookState, {"tool": "Edit", "path": "x.py"})
    assert payload is not None
""".lstrip(),
        "test_schema.py",
    )

    violations = detect_schema_bypasses(parsed)

    assert [(item.rule, item.identifier) for item in violations] == [
        ("schema-bypass-test-data", "test_payload_bypass:line-7")
    ]


def test_payload_detector_reports_presence_only_assertions(tmp_path: Path) -> None:
    parsed = parsed_file(
        tmp_path,
        """
def test_presence_only() -> None:
    result = build_result()
    assert result
""".lstrip(),
        "test_weak.py",
    )

    violations = detect_weak_assertions(parsed)

    assert [(item.rule, item.identifier) for item in violations] == [
        ("weak-test-assertion", "test_presence_only:line-3")
    ]


@given(IDENTIFIERS)
def test_hand_built_payload_detector_ignores_small_payloads_property(name: str) -> None:
    parsed = parsed_temp_source(
        f"def test_{name}() -> None:\n"
        "    payload = {'a': 1, 'b': 2}\n"
        "    assert payload['a'] == 1\n",
        "test_payload_property.py",
    )
    assert detect_hand_built_test_payloads(parsed) == []


@given(IDENTIFIERS)
def test_mock_theater_detector_ignores_semantic_assertions_property(name: str) -> None:
    parsed = parsed_temp_source(
        "from unittest.mock import Mock\n"
        f"def test_{name}() -> None:\n"
        "    handler = Mock(return_value='ok')\n"
        "    assert handler() == 'ok'\n",
        "test_mock_property.py",
    )
    assert detect_mock_theater(parsed) == []


@given(IDENTIFIERS)
def test_mocked_integration_detector_ignores_outer_boundary_patches_property(
    name: str,
) -> None:
    parsed = parsed_temp_source(
        "from unittest.mock import patch\n"
        f"def test_{name}_integration() -> None:\n"
        "    with patch('requests.get') as request:\n"
        "        request.return_value.status_code = 200\n"
        "        assert request.return_value.status_code == 200\n",
        "tests/integration/test_external_boundary.py",
    )
    assert detect_mocked_integration_tests(parsed) == []


@given(IDENTIFIERS)
def test_schema_bypass_detector_ignores_low_risk_casts_property(name: str) -> None:
    parsed = parsed_temp_source(
        "from typing import cast\n"
        f"def test_{name}() -> None:\n"
        "    value = cast(str, 'ok')\n"
        "    assert value == 'ok'\n",
        "test_schema_property.py",
    )
    assert detect_schema_bypasses(parsed) == []


@given(IDENTIFIERS)
def test_weak_assertion_detector_ignores_value_comparisons_property(name: str) -> None:
    parsed = parsed_temp_source(
        f"def test_{name}() -> None:\n"
        "    result = 3\n"
        "    assert result == 3\n",
        "test_weak_property.py",
    )
    assert detect_weak_assertions(parsed) == []
