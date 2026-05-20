from __future__ import annotations

from tests.test_test_integrity_lint import (
    Path,
    _assert_high_fan_in_style_helper_discount,
    _assert_holistic_suite_gap_report,
    _assert_runtime_coverage_report,
    _run_test_integrity,
    _write_holistic_suite_gap_project,
    _write_project,
    _write_runtime_coverage_project,
    pytest,
)

def test_lint_test_integrity_reports_holistic_suite_gaps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_holistic_suite_gap_project(tmp_path)

    result = _run_test_integrity(tmp_path, monkeypatch, details=True)

    captured = capsys.readouterr()
    assert result == 1
    _assert_holistic_suite_gap_report(captured.out)

def test_lint_test_integrity_uses_runtime_coverage_json_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_runtime_coverage_project(tmp_path)

    result = _run_test_integrity(tmp_path, monkeypatch, details=True)

    captured = capsys.readouterr()
    assert result == 1
    assert "coverage.json" in captured.out
    _assert_runtime_coverage_report(captured.out, result)

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
    assert "pkg.styles.markup" not in captured.out
    _assert_high_fan_in_style_helper_discount(captured.out, result)

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
