"""Constant-index discovery skips excluded directories."""

from __future__ import annotations

from pathlib import Path

from slopgate.quality.constant_index import iter_constant_candidate_paths


def test_iter_constant_candidate_paths_skips_git_dir(tmp_path: Path) -> None:
    hidden = tmp_path / ".git" / "constants.py"
    hidden.parent.mkdir()
    hidden.write_text('HIDDEN = "nope"\n', encoding="utf-8")
    visible = tmp_path / "constants.py"
    visible.write_text('API_URL = "https://example.test"\n', encoding="utf-8")
    assert iter_constant_candidate_paths(tmp_path) == [visible]
