"""Focused lint tests for test-integrity sniffers."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from slopgate.cli.lint import cmd_lint
from slopgate.cli.parsers import build_parser
from slopgate.lint._config import reset_config


def write_project(
    root: Path, test_body: str, *, test_name: str = "test_bad.py"
) -> None:
    (root / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    src = root / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    tests = root / "tests"
    tests.mkdir()
    (tests / test_name).write_text(test_body, encoding="utf-8")


def run_test_integrity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    details: bool = False,
) -> int:
    monkeypatch.chdir(tmp_path)
    reset_config()
    try:
        return cmd_lint(
            argparse.Namespace(lint_command="test-integrity", details=details)
        )
    finally:
        reset_config()


def run_lint_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    details: bool = False,
) -> int:
    monkeypatch.chdir(tmp_path)
    reset_config()
    try:
        return cmd_lint(argparse.Namespace(lint_command="check", details=details))
    finally:
        reset_config()


def assert_mock_theater_guidance(output: str, result: int) -> None:
    assert result == 1, "mock-theater fixture should fail test-integrity lint"
    expected_guidance = [
        "[NEW] mock-theater",
        "call-only mock assertions",
        "agent-context:",
        "source-snippet:",
        "test-under-review: test_sends_notice",
        "nearby-assertions:",
        "neighboring-tests:",
        "validation: .venv/bin/python -m pytest tests/test_bad.py -q",
        "assert semantic payloads or observable outputs",
    ]
    missing_guidance = [line for line in expected_guidance if line not in output]
    assert missing_guidance == [], "mock-theater report should include repair guidance"


def assert_schema_bypass_and_weak_assertion_report(output: str, result: int) -> None:
    assert result == 1, "weak assertion/schema bypass fixture should fail lint"
    expected_report = [
        "[NEW] weak-test-assertion",
        "[NEW] schema-bypass-test-data",
        "cast(OrchestrationState, dict literal)",
        "[NEW] hand-built-test-payload",
        "real model constructors",
        "correction-options: replace the presence check with exact content/state/output",
        "repo-hint: inspect nearest conftest.py",
        "required-proof: write the sentence",
        "which broken production line/seam",
    ]
    missing_report = [line for line in expected_report if line not in output]
    assert missing_report == [], (
        "schema bypass report should include model-constructor recovery"
    )


def assert_mocked_integration_report(output: str, result: int) -> None:
    assert result == 1, "mocked integration fixture should fail test-integrity lint"
    expected_report = [
        "[NEW] mocked-integration-test",
        "internal mock variable parser",
        "parser → enrichment → store/projection",
    ]
    missing_report = [line for line in expected_report if line not in output]
    assert missing_report == [], "mocked integration report should name mocked seam"


def assert_runtime_coverage_report(output: str, result: int) -> None:
    assert result == 1, "runtime coverage gap should fail test-integrity lint"
    expected_report = [
        "metadata.coverage_kind: runtime-line",
        "metadata.coverage_source: coverage.json",
        "metadata.coverage_percent: 37",
    ]
    missing_report = [line for line in expected_report if line not in output]
    assert missing_report == [], (
        "runtime coverage report should include coverage source metadata"
    )


def assert_high_fan_in_style_helper_discount(output: str, result: int) -> None:
    assert result == 1, "untested helper fixture should still report uncovered code"
    assert "[NEW] untested-public-api" in output, (
        "style-helper discount should not hide untested-public-api"
    )
    forbidden_report = [
        line
        for line in ["missing-integration-test", "pkg.styles.markup"]
        if line in output
    ]
    assert forbidden_report == [], (
        "high-fan-in style helpers should not force integration seam findings"
    )


HOLISTIC_CORE_SOURCE = """
def uncovered() -> str:
    return "missing"


def covered() -> str:
    return "ok"


def seam(value: int) -> int:
    return value + 1


def caller_a() -> int:
    return seam(1)


def caller_b() -> int:
    return seam(2)


def transform(text: str, options: dict[str, int]) -> list[str]:
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if options.get("limit", 0) > 0:
        parts = parts[: options["limit"]]
    return sorted(parts)


def old_api() -> str:
    '''Deprecated compatibility API.'''
    return "old"
""".lstrip()


def write_holistic_suite_gap_project(tmp_path: Path) -> None:
    write_project(
        tmp_path,
        """
from pkg.core import covered, old_api, transform
from pkg.removed import Missing


def test_covered_behavior():
    assert covered() == "ok"


def test_transform_examples():
    assert transform("a,b", {"limit": 2}) == ["a", "b"]


def test_old_api_compatibility():
    assert old_api() == "old"
""".lstrip(),
    )
    (tmp_path / "src" / "pkg" / "core.py").write_text(
        HOLISTIC_CORE_SOURCE,
        encoding="utf-8",
    )


def assert_holistic_suite_gap_report(output: str) -> None:
    expected = (
        "  src:     ",
        "[NEW] untested-public-api",
        "metadata.coverage_kind: static-reference",
        "metadata.unreferenced_symbols: uncovered",
        "[NEW] missing-integration-test",
        "production_callers=2",
        "[NEW] hypothesis-candidate",
        "property_test_score=",
        "[NEW] obsolete-or-deprecated-test",
        "imports missing production module `pkg.removed`",
        "test references deprecated production function `pkg.core.old_api`",
        "add one thin integration/contract test",
        "add a small Hypothesis property",
    )
    missing = [fragment for fragment in expected if fragment not in output]
    assert missing == [], "holistic report should include every repair signal"


def write_runtime_coverage_project(tmp_path: Path) -> None:
    write_project(
        tmp_path,
        """
from pkg.core import covered


def test_covered_behavior():
    assert covered() == "ok"
""".lstrip(),
    )
    (tmp_path / "src" / "pkg" / "core.py").write_text(
        """
def covered() -> str:
    return "ok"


def runtime_low() -> str:
    return "low"
""".lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "coverage.json").write_text(
        """{
  "files": {
    "src/pkg/core.py": {"summary": {"percent_covered": 37.2}}
  }
}
""",
        encoding="utf-8",
    )


def _write_project_root_bootstrap_package(tmp_path: Path) -> None:
    cloud_pkg = tmp_path / "cloud" / "services" / "opportunity"
    cloud_pkg.mkdir(parents=True)
    (tmp_path / "cloud" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "cloud" / "services" / "__init__.py").write_text("", encoding="utf-8")
    (cloud_pkg / "__init__.py").write_text("", encoding="utf-8")
    (cloud_pkg / "bootstrap.py").write_text(
        'def configure_opportunity_dependencies() -> str:\n    return "configured"\n',
        encoding="utf-8",
    )


def _write_src_cloud_module(tmp_path: Path) -> None:
    (tmp_path / "src" / "cloud").mkdir(parents=True)
    (tmp_path / "src" / "cloud" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "cloud" / "other.py").write_text(
        "def covered() -> str:\n    return 'ok'\n",
        encoding="utf-8",
    )


def test_obsolete_detector_allows_existing_project_root_bootstrap_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Production bootstrap imports in tests are valid when the module exists."""
    write_project(
        tmp_path,
        """
from cloud.services.opportunity.bootstrap import configure_opportunity_dependencies


def test_bootstrap_import_contract():
    assert configure_opportunity_dependencies() == "configured"
""".lstrip(),
    )
    _write_project_root_bootstrap_package(tmp_path)
    _write_src_cloud_module(tmp_path)

    result = run_test_integrity(tmp_path, monkeypatch, details=True)
    output = capsys.readouterr().out

    assert result == 1
    assert (
        "imports missing production module `cloud.services.opportunity.bootstrap`"
        not in output
    )


# Exported test support used by split test modules.
__all__ = (
    "Path",
    "assert_high_fan_in_style_helper_discount",
    "assert_holistic_suite_gap_report",
    "assert_mock_theater_guidance",
    "assert_mocked_integration_report",
    "assert_runtime_coverage_report",
    "assert_schema_bypass_and_weak_assertion_report",
    "run_lint_check",
    "run_test_integrity",
    "write_holistic_suite_gap_project",
    "write_project",
    "write_runtime_coverage_project",
    "argparse",
    "build_parser",
    "cmd_lint",
    "pytest",
    "reset_config",
)
