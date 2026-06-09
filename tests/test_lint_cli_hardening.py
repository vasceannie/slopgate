"""CLI lint hardening tests."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from slopgate.cli.lint import _LintRunTotals, _TallyInput, _print_lint_summary, _tally_rule, cmd_lint
from slopgate.lint._baseline import Violation, assert_no_new_violations
from slopgate.lint._config import reset_config
from slopgate.lint._details import format_violation_details


def _write_clean_project(root: Path) -> Path:
    (root / "slopgate.toml").write_text("[slopgate]\nenabled = true\n", encoding="utf-8")
    src_pkg = root / "src" / "pkg"
    src_pkg.mkdir(parents=True)
    (src_pkg / "clean.py").write_text(
        "from __future__ import annotations\n\n\ndef answer() -> int:\n    return 1\n",
        encoding="utf-8",
    )
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_clean.py").write_text(
        "from pkg.clean import answer\n\n\ndef test_answer_contract() -> None:\n    assert answer() == 1\n",
        encoding="utf-8",
    )
    return src_pkg


def _assert_lint_check_forces_repo_root_scope(
    output: str, project_root: Path, result: int
) -> None:
    assert result == 0, "clean nested lint check should return success"
    expected_lines = [
        f"project:  {project_root}",
        f"src:     {project_root / 'src'}  (1 files)",
        "✓ No violations",
    ]
    missing_lines = [line for line in expected_lines if line not in output]
    assert missing_lines == [], "lint check should ignore changed scope and scan repo root"


def _assert_prescriptive_details_for_oversized_module(output: str, result: int) -> None:
    assert result == 1, "oversized module should fail lint check"
    expected_details = [
        "[NEW] oversized-module-soft",
        "file: src/large.py",
        "signature: module `large.py`",
        "src/large/__init__.py",
        "prognosis: one module owns multiple responsibilities",
    ]
    missing_details = [detail for detail in expected_details if detail not in output]
    assert missing_details == [], "--details should emit prescriptive oversized-module block"


def _assert_oversized_module_scaffold(block: str) -> None:
    expected_scaffold = [
        "[NEW] oversized-module",
        "file: src/example/large.py",
        "signature: module `large.py`",
        "stable-id: oversized-module|src/example/large.py|large.py",
        "src/example/large/__init__.py",
        "models.py, parsing.py, services.py",
    ]
    missing_scaffold = [entry for entry in expected_scaffold if entry not in block]
    assert missing_scaffold == [], "oversized module detail block should name split scaffold"


def _assert_type_suppression_detail_block(block: str) -> None:
    expected_details = [
        "[KNOWN-DEBT] type-suppression",
        "location: src/example/types.py:12",
        "metadata.related_files: src/example/protocols.py",
        "Protocol, TypedDict, overload, local stub",
    ]
    missing_details = [detail for detail in expected_details if detail not in block]
    assert missing_details == [], "type suppression detail block should include metadata and prognosis"


def _write_lint_project_with_file(root: Path, rel_path: str, content: str) -> None:
    (root / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n",
        encoding="utf-8",
    )
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    (root / "tests").mkdir(exist_ok=True)


def _run_lint_check(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    cwd: Path,
    *,
    details: bool,
) -> tuple[int, str]:
    monkeypatch.chdir(cwd)
    reset_config()
    try:
        result = cmd_lint(argparse.Namespace(lint_command="check", details=details))
    finally:
        reset_config()
    captured = capsys.readouterr()
    return result, captured.out


def test_lint_check_discovers_project_root_and_forces_all_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    nested_cwd = _write_clean_project(tmp_path)
    monkeypatch.setenv("QUALITY_SCOPE", "changed")
    result, output = _run_lint_check(monkeypatch, capsys, nested_cwd, details=False)

    assert result == 0
    _assert_lint_check_forces_repo_root_scope(output, tmp_path, result)


def test_lint_check_details_outputs_prescriptive_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_lint_project_with_file(
        tmp_path,
        "src/large.py",
        "from __future__ import annotations\n" + "# filler\n" * 370,
    )
    result, output = _run_lint_check(monkeypatch, capsys, tmp_path, details=True)

    assert result == 1
    _assert_prescriptive_details_for_oversized_module(output, result)


def test_lint_check_flags_ty_ignore_as_type_suppression(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_lint_project_with_file(
        tmp_path,
        "src/types.py",
        "from __future__ import annotations\n\n"
        "def identity(value: object) -> object:\n"
        "    return value  # ty: ignore[possibly-unbound]\n",
    )
    result, output = _run_lint_check(monkeypatch, capsys, tmp_path, details=True)

    assert result == 1
    assert "[NEW] type-suppression" in output
    assert "# ty: ignore[possibly-unbound]" in output


def test_quality_generate_baseline_env_does_not_hide_new_violations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_lint_project_with_file(
        tmp_path,
        "src/example.py",
        "from __future__ import annotations\n\ndef answer() -> int:\n    return 1\n",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUALITY_GENERATE_BASELINE", "1")
    reset_config()
    try:
        with pytest.raises(AssertionError, match="1 NEW violation"):
            assert_no_new_violations(
                "manual-rule",
                [Violation("manual-rule", "src/example.py", "answer")],
            )
    finally:
        reset_config()


def test_lint_details_formatter_includes_prescriptive_scaffold() -> None:
    violation = Violation(
        rule="oversized-module",
        relative_path="src/example/large.py",
        identifier="large.py",
        detail="lines=742 (hard limit=600)",
    )

    block = "\n".join(
        format_violation_details("oversized-module", violation, status="NEW")
    )

    assert "[NEW] oversized-module" in block
    _assert_oversized_module_scaffold(block)


def test_lint_details_formatter_reports_metadata_and_type_prognosis() -> None:
    violation = Violation(
        rule="type-suppression",
        relative_path="src/example/types.py",
        identifier="line-12",
        detail="# type: ignore[assignment]",
        metadata={"related_files": ["src/example/protocols.py"]},
    )

    block = "\n".join(
        format_violation_details("type-suppression", violation, status="KNOWN-DEBT")
    )

    assert "metadata.related_files" in block
    _assert_type_suppression_detail_block(block)


def test_lint_summary_clean_repo_says_no_violations(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _print_lint_summary(_LintRunTotals(0, 0, 0), color=False) == 0
    output = capsys.readouterr().out
    assert "✓ No violations" in output
    assert "baselines.json" not in output


def test_lint_summary_prints_existing_literal_locations(
    capsys: pytest.CaptureFixture[str],
) -> None:
    violation = Violation(
        rule="repeated-string-literal",
        relative_path="<project>",
        identifier="'skipped'",
        detail=(
            "appears in 11 files (max: 10); locations: src/a.py:5, src/b.py:8; "
            "consider `SKIPPED`"
        ),
        metadata={"existing_locations": ["src/a.py:5", "src/b.py:8"]},
    )

    _ = _tally_rule(
        _TallyInput(
            rule_name="repeated-string-literal",
            violations=[violation],
            baseline={},
            details=False,
        )
    )

    output = capsys.readouterr().out
    assert "+ <project>:'skipped'" in output
    assert "locations: src/a.py:5, src/b.py:8" in output
    assert "existing locations:" not in output


def test_lint_summary_falls_back_to_metadata_locations_without_detail_suffix(
    capsys: pytest.CaptureFixture[str],
) -> None:
    violation = Violation(
        rule="repeated-string-literal",
        relative_path="<project>",
        identifier="'skipped'",
        detail="appears in 11 files (max: 10); consider `SKIPPED`",
        metadata={"existing_locations": ["src/a.py:5", "src/b.py:8"]},
    )

    _ = _tally_rule(
        _TallyInput(
            rule_name="repeated-string-literal",
            violations=[violation],
            baseline={},
            details=False,
        )
    )

    output = capsys.readouterr().out
    assert "existing locations: src/a.py:5, src/b.py:8" in output
