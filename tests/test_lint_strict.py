from __future__ import annotations

from pathlib import Path

from slopgate.cli.lint import lint_check, lint_freeze, lint_strict
from tests.lint_paths_support import seed_freeze_repo


def test_lint_check_passes_when_only_known_debt(tmp_path: Path) -> None:
    seed_freeze_repo(tmp_path)
    assert (lint_freeze(tmp_path), lint_check(tmp_path)) == (0, 0)


def test_lint_strict_fails_when_only_known_debt(tmp_path: Path) -> None:
    seed_freeze_repo(tmp_path)
    assert (lint_freeze(tmp_path), lint_strict(tmp_path)) == (0, 1)
