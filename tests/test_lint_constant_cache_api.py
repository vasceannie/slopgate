"""Contracts for enrolled constant-index SQLite reuse."""

from __future__ import annotations

from pathlib import Path

from slopgate.lint.project_index.constant_cache import load_constant_index, save_constant_index
from slopgate.quality.constant_index import ConstantIndex, StringConstantMatch


def _saved_constants(root: Path) -> Path:
    (root / "slopgate.toml").write_text("[slopgate]\nenabled = true\n", encoding="utf-8")
    constants = root / "src/pkg/constants.py"
    constants.parent.mkdir(parents=True, exist_ok=True)
    constants.write_text('NAME = "alpha"\n', encoding="utf-8")
    index = ConstantIndex(
        root=root.resolve(),
        string_constants={
            "alpha": [StringConstantMatch(name="NAME", path=constants, lineno=1)]
        },
        files=(constants,),
    )
    save_constant_index(root, index)
    return constants


def test_load_constant_index_hits_saved_payload(tmp_path: Path) -> None:
    _saved_constants(tmp_path)
    loaded = load_constant_index(tmp_path, ())
    assert loaded is not None and loaded.string_constants["alpha"][0].name == "NAME"


def test_load_constant_index_misses_dirty_constants_file(tmp_path: Path) -> None:
    constants = _saved_constants(tmp_path)
    assert load_constant_index(tmp_path, (constants,)) is None
