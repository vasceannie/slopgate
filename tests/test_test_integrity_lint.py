"""Focused lint tests for test-integrity sniffers."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from vibeforcer.cli.lint import cmd_lint
from vibeforcer.cli.parsers import build_parser
from vibeforcer.lint._config import reset_config


def _write_project(root: Path, test_body: str, *, test_name: str = "test_bad.py") -> None:
    (root / "quality_gate.toml").write_text("[quality_gate]\nenabled = true\n", encoding="utf-8")
    src = root / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    tests = root / "tests"
    tests.mkdir()
    (tests / test_name).write_text(test_body, encoding="utf-8")


def _run_test_integrity(
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


def test_lint_test_integrity_parser_wires_subcommand() -> None:
    parser = build_parser()

    args = parser.parse_args(["lint", "test-integrity", "--details"])

    assert args.command == "lint"
    assert args.lint_command == "test-integrity"
    assert args.details is True


def test_lint_test_integrity_flags_mock_theater_with_guidance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_project(
        tmp_path,
        """
from unittest.mock import MagicMock


def test_sends_notice():
    sender = MagicMock()
    sender({"company": "Acme"})
    sender.assert_called_once()


def test_sends_notice_payload_contract():
    sender = MagicMock()
    sender({"company": "Acme"})
    sender.assert_called_once_with({"company": "Acme"})
""".lstrip(),
    )

    result = _run_test_integrity(tmp_path, monkeypatch, details=True)

    captured = capsys.readouterr()
    assert result == 1
    assert "[NEW] mock-theater" in captured.out
    assert "call-only mock assertions" in captured.out
    assert "agent-context:" in captured.out
    assert "source-snippet:" in captured.out
    assert "test-under-review: test_sends_notice" in captured.out
    assert "nearby-assertions:" in captured.out
    assert "neighboring-tests:" in captured.out
    assert "validation: .venv/bin/python -m pytest tests/test_bad.py -q" in captured.out
    assert "assert semantic payloads or observable outputs" in captured.out


def test_lint_test_integrity_flags_weak_assertions_and_schema_bypasses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_project(
        tmp_path,
        """
from typing import cast


class OrchestrationState(dict[str, object]):
    pass


def test_projection_payload_survives():
    result = object()
    assert result is not None
    state = {"company": None, "job_id": "1", "field": "title", "status": "ok"}
    typed_state = cast(OrchestrationState, {"company": None, "job_id": "1", "field": "title", "status": "ok"})
    assert len(state) > 0
    assert typed_state is not None
""".lstrip(),
    )

    result = _run_test_integrity(tmp_path, monkeypatch, details=True)

    captured = capsys.readouterr()
    assert result == 1
    assert "[NEW] weak-test-assertion" in captured.out
    assert "[NEW] schema-bypass-test-data" in captured.out
    assert "cast(OrchestrationState, dict literal)" in captured.out
    assert "[NEW] hand-built-test-payload" in captured.out
    assert "real model constructors" in captured.out
    assert "correction-options: replace the presence check with exact content/state/output" in captured.out
    assert "repo-hint: inspect nearest conftest.py" in captured.out
    assert "required-proof: write the sentence" in captured.out
    assert "which broken production line/seam" in captured.out


def test_lint_test_integrity_allows_semantic_mock_payload_assertion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_project(
        tmp_path,
        """
from unittest.mock import MagicMock


def test_publishes_company_payload():
    publisher = MagicMock()
    publisher({"company": "Acme"})
    publisher.assert_called_once_with({"company": "Acme"})
""".lstrip(),
    )

    result = _run_test_integrity(tmp_path, monkeypatch)

    captured = capsys.readouterr()
    assert result == 0
    assert "No new violations" in captured.out


def test_lint_test_integrity_flags_mocked_integration_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_project(
        tmp_path,
        """
from unittest.mock import MagicMock


def test_e2e_projection_pipeline_renders_company():
    parser = MagicMock()
    parser.return_value = {"company": "Acme"}
    assert parser.return_value == {"company": "Acme"}
""".lstrip(),
        test_name="test_tui_integration.py",
    )

    result = _run_test_integrity(tmp_path, monkeypatch, details=True)

    captured = capsys.readouterr()
    assert result == 1
    assert "[NEW] mocked-integration-test" in captured.out
    assert "internal mock variable parser" in captured.out
    assert "parser → enrichment → store/projection" in captured.out


def test_lint_test_integrity_allows_type_guard_before_semantic_assertions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_project(
        tmp_path,
        """
def test_error_context_is_preserved():
    result = {"error": {"source": "parser", "context": {"company": "Acme"}}}
    error = result.get("error")
    assert error is not None
    assert error["source"] == "parser"
    assert error["context"] == {"company": "Acme"}
""".lstrip(),
    )

    result = _run_test_integrity(tmp_path, monkeypatch)

    captured = capsys.readouterr()
    assert result == 0
    assert "No new violations" in captured.out


def test_lint_test_integrity_allows_negative_side_effect_mock_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_project(
        tmp_path,
        """
from unittest.mock import MagicMock


def test_noop_does_not_log_without_start_time():
    mock_log = MagicMock()
    if False:
        mock_log("unexpected")
    mock_log.assert_not_called()
""".lstrip(),
    )

    result = _run_test_integrity(tmp_path, monkeypatch)

    captured = capsys.readouterr()
    assert result == 0
    assert "No new violations" in captured.out


def test_lint_test_integrity_ignores_low_risk_wire_payload_contracts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_project(
        tmp_path,
        """
from typing import cast

JsonObject = dict[str, object]


def test_deserialize_ignores_unknown_fields():
    payload = {"type": "event", "id": "1", "company": "Acme", "unknown": True}
    wire = cast(JsonObject, {"type": "event", "id": "1", "unknown": True})
    assert payload["type"] == "event"
    assert wire["id"] == "1"
""".lstrip(),
        test_name="test_deserialize_contract.py",
    )

    result = _run_test_integrity(tmp_path, monkeypatch)

    captured = capsys.readouterr()
    assert result == 0
    assert "No new violations" in captured.out


def test_lint_test_integrity_allows_outer_boundary_stubs_in_integration_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_project(
        tmp_path,
        """
from unittest.mock import patch


def test_integration_bootstrap_uses_env_boundary():
    with patch("os.environ", {"API_URL": "http://example.test"}):
        rendered = "company=Acme"
    assert rendered == "company=Acme"
""".lstrip(),
        test_name="test_bootstrap_integration.py",
    )

    result = _run_test_integrity(tmp_path, monkeypatch)

    captured = capsys.readouterr()
    assert result == 0
    assert "No new violations" in captured.out


def test_lint_test_integrity_allows_one_field_protocol_namespace_stub(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_project(
        tmp_path,
        """
from types import SimpleNamespace


def test_soft_verify_widget_kind_protocol_stub():
    field = SimpleNamespace(widget_kind="textbox")
    assert field.widget_kind == "textbox"
""".lstrip(),
    )

    result = _run_test_integrity(tmp_path, monkeypatch)

    captured = capsys.readouterr()
    assert result == 0
    assert "No new violations" in captured.out


def test_lint_test_integrity_flags_richer_namespace_fake_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_project(
        tmp_path,
        """
from types import SimpleNamespace


def test_fake_field_model_drift():
    field = SimpleNamespace(control_id="email", company="Acme")
    assert field.control_id == "email"
""".lstrip(),
    )

    result = _run_test_integrity(tmp_path, monkeypatch)

    captured = capsys.readouterr()
    assert result == 1
    assert "schema-bypass-test-data" in captured.out


def test_lint_test_integrity_reports_holistic_suite_gaps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_project(
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
        """
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
""".lstrip(),
        encoding="utf-8",
    )

    result = _run_test_integrity(tmp_path, monkeypatch, details=True)

    captured = capsys.readouterr()
    assert result == 1
    assert "  src:     " in captured.out
    assert "[NEW] untested-production-code" in captured.out
    assert "static_test_reference_coverage=" in captured.out
    assert "unreferenced=uncovered" in captured.out
    assert "[NEW] missing-integration-test" in captured.out
    assert "production_callers=2" in captured.out
    assert "[NEW] hypothesis-candidate" in captured.out
    assert "property_test_score=" in captured.out
    assert "[NEW] obsolete-or-deprecated-test" in captured.out
    assert "imports missing production module `pkg.removed`" in captured.out
    assert "test references deprecated production function `pkg.core.old_api`" in captured.out
    assert "add one thin integration/contract test" in captured.out
    assert "add a small Hypothesis property" in captured.out


def test_lint_test_integrity_uses_runtime_coverage_json_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_project(
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

    result = _run_test_integrity(tmp_path, monkeypatch, details=True)

    captured = capsys.readouterr()
    assert result == 1
    assert "runtime_line_coverage=37% from coverage.json" in captured.out
    assert "metadata.coverage_kind: runtime-line" in captured.out
    assert "metadata.coverage_source: coverage.json" in captured.out


def test_lint_test_integrity_discounts_high_fan_in_style_helpers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_project(
        tmp_path,
        """
def test_smoke():
    assert "ok" == "ok"
""".lstrip(),
    )
    (tmp_path / "src" / "pkg" / "styles.py").write_text(
        """
def markup(value: str) -> str:
    return f"<b>{value}</b>"


def caller_a() -> str:
    return markup("a")


def caller_b() -> str:
    return markup("b")


def caller_c() -> str:
    return markup("c")
""".lstrip(),
        encoding="utf-8",
    )

    result = _run_test_integrity(tmp_path, monkeypatch, details=True)

    captured = capsys.readouterr()
    assert result == 1
    assert "[NEW] untested-production-code" in captured.out
    assert "missing-integration-test" not in captured.out
    assert "pkg.styles.markup" not in captured.out


def test_lint_test_integrity_reports_deprecated_replacement_hint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_project(
        tmp_path,
        """
from pkg.core import old_api


def test_old_api_compatibility():
    assert old_api() == "old"
""".lstrip(),
    )
    (tmp_path / "src" / "pkg" / "core.py").write_text(
        """
def old_api() -> str:
    '''Deprecated compatibility API. Use new_api instead.'''
    return "old"


def new_api() -> str:
    return "new"
""".lstrip(),
        encoding="utf-8",
    )

    result = _run_test_integrity(tmp_path, monkeypatch, details=True)

    captured = capsys.readouterr()
    assert result == 1
    assert "replacement=new_api" in captured.out
    assert "metadata.replacement: new_api" in captured.out
