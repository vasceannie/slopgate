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


def test_lint_test_integrity_normalizes_backslash_runtime_coverage_json_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_runtime_coverage_project(tmp_path)
    (tmp_path / "coverage.json").write_text(
        """{
  "files": {
    "src\\\\pkg\\\\core.py": {"summary": {"percent_covered": 37.2}}
  }
}
""",
        encoding="utf-8",
    )

    result = _run_test_integrity(tmp_path, monkeypatch, details=True)

    captured = capsys.readouterr()
    assert result == 1
    assert "runtime_line_coverage=37% from coverage.json" in captured.out


def test_lint_test_integrity_normalizes_backslash_runtime_coverage_xml_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_runtime_coverage_project(tmp_path)
    (tmp_path / "coverage.json").unlink()
    (tmp_path / "coverage.xml").write_text(
        """<?xml version="1.0" ?>
<coverage line-rate="0.37" branch-rate="0" version="coverage.py">
  <packages>
    <package name="pkg" line-rate="0.37">
      <classes>
        <class name="core.py" filename="src\\pkg\\core.py" line-rate="0.37" />
      </classes>
    </package>
  </packages>
</coverage>
""",
        encoding="utf-8",
    )

    result = _run_test_integrity(tmp_path, monkeypatch, details=True)

    captured = capsys.readouterr()
    assert result == 1
    assert "runtime_line_coverage=37% from coverage.xml" in captured.out


def _write_cobertura_xml_source_project(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        """
from pkg.core import covered, runtime_low


def test_covered_behavior():
    assert covered() == "ok"
    assert runtime_low() == "low"
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
    (tmp_path / "coverage.xml").write_text(
        f"""<?xml version="1.0" ?>
<coverage line-rate="0.91" branch-rate="0" version="coverage.py">
  <sources><source>{tmp_path / "src"}</source></sources>
  <packages><package name="pkg" line-rate="0.91"><classes>
    <class name="core.py" filename="pkg/core.py" line-rate="0.91" />
  </classes></package></packages>
</coverage>
""",
        encoding="utf-8",
    )


def test_lint_test_integrity_uses_cobertura_xml_sources_for_src_relative_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_cobertura_xml_source_project(tmp_path)

    result = _run_test_integrity(tmp_path, monkeypatch, details=True)

    captured = capsys.readouterr()
    assert result == 0
    assert "runtime_line_coverage=0% from coverage.xml" not in captured.out


def _write_partial_runtime_coverage_project(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        """
from pkg.core import covered


def test_focused_public_behavior():
    assert covered() == "ok"
""".lstrip(),
    )
    (tmp_path / "src" / "pkg" / "core.py").write_text(
        """
def covered() -> str:
    return "ok"
""".lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "src" / "pkg" / "other.py").write_text(
        """
def other_behavior() -> str:
    return "other"
""".lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "coverage.xml").write_text(
        f"""<?xml version="1.0" ?>
<coverage line-rate="1" branch-rate="0" version="coverage.py">
  <sources><source>{tmp_path / "src"}</source></sources>
  <packages><package name="pkg" line-rate="1"><classes>
    <class name="core.py" filename="pkg/core.py" line-rate="1" />
  </classes></package></packages>
</coverage>
""",
        encoding="utf-8",
    )


def test_lint_test_integrity_treats_absent_partial_runtime_coverage_as_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_partial_runtime_coverage_project(tmp_path)

    result = _run_test_integrity(tmp_path, monkeypatch, details=True)

    captured = capsys.readouterr()
    forbidden = ["src/pkg/other.py:coverage-000", "runtime_line_coverage=0% from coverage.xml"]
    assert result == 0
    assert all(item not in captured.out for item in forbidden)


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
