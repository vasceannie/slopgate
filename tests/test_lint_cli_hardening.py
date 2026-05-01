"""CLI lint hardening tests."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from vibeforcer.cli.lint import cmd_lint
from vibeforcer.lint._baseline import Violation
from vibeforcer.lint._config import reset_config
from vibeforcer.lint._details import format_violation_details


def _write_clean_project(root: Path) -> Path:
    (root / "quality_gate.toml").write_text("[quality_gate]\nenabled = true\n", encoding="utf-8")
    src_pkg = root / "src" / "pkg"
    src_pkg.mkdir(parents=True)
    (src_pkg / "clean.py").write_text(
        "from __future__ import annotations\n\n\ndef answer() -> int:\n    return 1\n",
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    return src_pkg


def test_lint_check_discovers_project_root_and_forces_all_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    nested_cwd = _write_clean_project(tmp_path)
    monkeypatch.chdir(nested_cwd)
    monkeypatch.setenv("QUALITY_SCOPE", "changed")
    reset_config()
    try:
        result = cmd_lint(argparse.Namespace(lint_command="check", details=False))
    finally:
        reset_config()

    captured = capsys.readouterr()
    assert result == 0
    assert f"project: {tmp_path}" in captured.out
    assert f"src:     {tmp_path / 'src'}  (1 files)" in captured.out
    assert "✓ No new violations" in captured.out


def test_lint_check_details_outputs_prescriptive_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "quality_gate.toml").write_text(
        "[quality_gate]\nenabled = true\n",
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "large.py").write_text(
        "from __future__ import annotations\n" + "# filler\n" * 370,
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    monkeypatch.chdir(tmp_path)
    reset_config()
    try:
        result = cmd_lint(argparse.Namespace(lint_command="check", details=True))
    finally:
        reset_config()

    captured = capsys.readouterr()
    assert result == 1
    assert "[NEW] oversized-module-soft" in captured.out
    assert "file: src/large.py" in captured.out
    assert "signature: module `large.py`" in captured.out
    assert "src/large/__init__.py" in captured.out
    assert "prognosis: one module owns multiple responsibilities" in captured.out


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
    assert "file: src/example/large.py" in block
    assert "signature: module `large.py`" in block
    assert "stable-id: oversized-module|src/example/large.py|large.py" in block
    assert "src/example/large/__init__.py" in block
    assert "models.py, parsing.py, services.py" in block


def test_lint_details_formatter_reports_metadata_and_type_prognosis() -> None:
    violation = Violation(
        rule="type-suppression",
        relative_path="src/example/types.py",
        identifier="line-12",
        detail="# type: ignore[assignment]",
        metadata={"related_files": ["src/example/protocols.py"]},
    )

    block = "\n".join(
        format_violation_details("type-suppression", violation, status="BASELINED")
    )

    assert "[BASELINED] type-suppression" in block
    assert "location: src/example/types.py:12" in block
    assert "metadata.related_files: src/example/protocols.py" in block
    assert "Protocol, TypedDict, overload, local stub" in block
