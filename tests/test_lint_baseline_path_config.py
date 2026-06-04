from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.lint._baseline import _baseline_path
from slopgate.lint._config import load_config, reset_config, set_config
from slopgate.lint._toml_overrides import resolve_baseline_path


@pytest.fixture(autouse=True)
def _reset_lint_config() -> None:
    yield
    reset_config()


def test_load_config_ignores_tests_quality_baselines_without_toml_override(
    tmp_path: Path,
) -> None:
    quality_dir = tmp_path / "tests" / "quality"
    quality_dir.mkdir(parents=True)
    _ = (quality_dir / "baselines.json").write_text(
        '{"schema_version": 1, "bool_equality_max": 2}',
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    set_config(cfg)

    assert cfg.baseline_path is None
    assert _baseline_path() == tmp_path / "baselines.json"


def test_load_config_honors_paths_baseline_path(tmp_path: Path) -> None:
    _ = (tmp_path / "slopgate.toml").write_text(
        '[paths]\nbaseline_path = "custom/baseline.json"\n',
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    set_config(cfg)

    assert cfg.baseline_path == tmp_path / "custom" / "baseline.json"
    assert _baseline_path() == tmp_path / "custom" / "baseline.json"


def test_resolve_baseline_path_supports_absolute_paths(tmp_path: Path) -> None:
    absolute = tmp_path / "elsewhere" / "baseline.json"
    absolute.parent.mkdir(parents=True)
    _ = (tmp_path / "slopgate.toml").write_text(
        f'[paths]\nbaseline_path = "{absolute.as_posix()}"\n',
        encoding="utf-8",
    )

    assert resolve_baseline_path(tmp_path) == absolute.resolve()
