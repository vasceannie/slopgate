"""Parallel parse attempts must keep project-relative paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.lint._config import load_config, set_config
from slopgate.lint._helpers.parsing import parse_file_attempts

MODULE_COUNT = 3


def test_parallel_parse_attempts_keep_project_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    src = project / "src"
    src.mkdir(parents=True)
    _ = (project / "pyproject.toml").write_text(
        "[project]\nname = 'parallel-parse'\n", encoding="utf-8"
    )
    paths = [src / f"module_{index}.py" for index in range(MODULE_COUNT)]
    for path in paths:
        _ = path.write_text("value = 1\n", encoding="utf-8")
    set_config(load_config(project))
    monkeypatch.setattr("slopgate.lint._helpers.parallel.LINT_PARALLEL_MIN_FILES", 1)

    attempts = parse_file_attempts(paths)

    rels = [attempt.parsed.rel for attempt in attempts if attempt.parsed is not None]
    assert rels == [f"src/module_{index}.py" for index in range(MODULE_COUNT)], (
        f"parallel workers must report project-relative paths, got {rels}"
    )
