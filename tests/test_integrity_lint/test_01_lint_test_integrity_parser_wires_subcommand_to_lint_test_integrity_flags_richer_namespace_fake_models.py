from __future__ import annotations

from pytest import MonkeyPatch, CaptureFixture

from tests.test_test_integrity_lint import (
    Path,
    assert_mock_theater_guidance,
    assert_mocked_integration_report,
    assert_schema_bypass_and_weak_assertion_report,
    run_lint_check,
    run_test_integrity,
    write_project,
    build_parser,
)


def test_lint_test_integrity_parser_wires_subcommand() -> None:
    parser = build_parser()

    args = parser.parse_args(["lint", "test-integrity", "--details"])

    assert (args.command, args.lint_command, args.details) == (
        "lint",
        "test-integrity",
        True,
    )


def test_lint_test_integrity_flags_mock_theater_with_guidance(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    write_project(
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

    result = run_test_integrity(tmp_path, monkeypatch, details=True)

    captured = capsys.readouterr()
    assert result == 1
    assert "[NEW] mock-theater" in captured.out
    assert_mock_theater_guidance(captured.out, result)


def test_main_lint_check_includes_test_integrity_findings(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    write_project(
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

    result = run_lint_check(tmp_path, monkeypatch, details=True)

    captured = capsys.readouterr()
    assert result == 1
    assert "slopgate lint " in captured.out
    assert "slopgate lint test-integrity" not in captured.out
    assert_mock_theater_guidance(captured.out, result)


def test_lint_test_integrity_flags_weak_assertions_and_schema_bypasses(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    write_project(
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

    result = run_test_integrity(tmp_path, monkeypatch, details=True)

    captured = capsys.readouterr()
    assert result == 1
    assert "[NEW] schema-bypass-test-data" in captured.out
    assert_schema_bypass_and_weak_assertion_report(captured.out, result)


def test_lint_test_integrity_allows_semantic_mock_payload_assertion(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    write_project(
        tmp_path,
        """
from unittest.mock import MagicMock


def test_publishes_company_payload():
    publisher = MagicMock()
    publisher({"company": "Acme"})
    publisher.assert_called_once_with({"company": "Acme"})
""".lstrip(),
    )

    result = run_test_integrity(tmp_path, monkeypatch)

    captured = capsys.readouterr()
    assert result == 0
    assert "✓ No violations" in captured.out


def test_lint_test_integrity_flags_mocked_integration_tests(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    write_project(
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

    result = run_test_integrity(tmp_path, monkeypatch, details=True)

    captured = capsys.readouterr()
    assert result == 1
    assert "[NEW] mocked-integration-test" in captured.out
    assert_mocked_integration_report(captured.out, result)


def test_lint_test_integrity_allows_type_guard_before_semantic_assertions(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    write_project(
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

    result = run_test_integrity(tmp_path, monkeypatch)

    captured = capsys.readouterr()
    assert result == 0
    assert "✓ No violations" in captured.out


def test_lint_test_integrity_allows_negative_side_effect_mock_contract(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    write_project(
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

    result = run_test_integrity(tmp_path, monkeypatch)

    captured = capsys.readouterr()
    assert result == 0
    assert "✓ No violations" in captured.out


def test_lint_test_integrity_ignores_low_risk_wire_payload_contracts(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    write_project(
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

    result = run_test_integrity(tmp_path, monkeypatch)

    captured = capsys.readouterr()
    assert result == 0
    assert "✓ No violations" in captured.out


def test_lint_test_integrity_allows_outer_boundary_stubs_in_integration_tests(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    write_project(
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

    result = run_test_integrity(tmp_path, monkeypatch)

    captured = capsys.readouterr()
    assert result == 0
    assert "✓ No violations" in captured.out


def test_lint_test_integrity_allows_one_field_protocol_namespace_stub(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    write_project(
        tmp_path,
        """
from types import SimpleNamespace


def test_soft_verify_widget_kind_protocol_stub():
    field = SimpleNamespace(widget_kind="textbox")
    assert field.widget_kind == "textbox"
""".lstrip(),
    )

    result = run_test_integrity(tmp_path, monkeypatch)

    captured = capsys.readouterr()
    assert result == 0
    assert "✓ No violations" in captured.out


def test_lint_test_integrity_flags_richer_namespace_fake_models(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    write_project(
        tmp_path,
        """
from types import SimpleNamespace


def test_fake_field_model_drift():
    field = SimpleNamespace(control_id="email", company="Acme")
    assert field.control_id == "email"
""".lstrip(),
    )

    result = run_test_integrity(tmp_path, monkeypatch)

    captured = capsys.readouterr()
    assert result == 1
    assert "schema-bypass-test-data" in captured.out
