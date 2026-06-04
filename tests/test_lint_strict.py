from __future__ import annotations

from pathlib import Path

from slopgate.cli.lint import _lint_check, _lint_freeze, _lint_strict
from tests.lint_paths_support import seed_freeze_repo


def test_lint_check_passes_when_only_known_debt(tmp_path: Path) -> None:
    seed_freeze_repo(tmp_path)
    assert (_lint_freeze(tmp_path), _lint_check(tmp_path)) == (0, 0)


def test_lint_strict_fails_when_only_known_debt(tmp_path: Path) -> None:
    seed_freeze_repo(tmp_path)
    assert (_lint_freeze(tmp_path), _lint_strict(tmp_path)) == (0, 1)
