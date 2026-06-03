"""QUALITY-LINT touched-source reference discovery regressions."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support import finding_ids
from vibeforcer.engine import evaluate_payload
from vibeforcer.lint._config import reset_config


def _write_referenced_source_project(repo: Path) -> Path:
    (repo / "quality_gate.toml").write_text(
        "[quality_gate]\nenabled = true\n",
        encoding="utf-8",
    )
    src_dir = repo / "src" / "pkg"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text("", encoding="utf-8")
    source_path = src_dir / "core.py"
    source_path.write_text(
        """
def covered() -> str:
    return "ok"
""".lstrip(),
        encoding="utf-8",
    )
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_core.py").write_text(
        """
from pkg.core import covered


def test_covered_behavior():
    assert covered() == "ok"
""".lstrip(),
        encoding="utf-8",
    )
    return source_path


def test_quality_lint_reference_tests_ignore_changed_scope_for_touched_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = _write_referenced_source_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QUALITY_SCOPE", "changed")
    reset_config()
    try:
        result = evaluate_payload(
            {
                "session_id": "scope-regression",
                "cwd": str(tmp_path),
                "hook_event_name": "PostToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": str(source_path)},
            }
        )
    finally:
        reset_config()

    assert "QUALITY-LINT-001" not in finding_ids(result)
