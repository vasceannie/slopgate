from __future__ import annotations

from pathlib import Path

from slopgate.lint._baseline import baseline_path
from slopgate.lint._config import load_config, set_config
from slopgate.lint._toml_overrides import resolve_baseline_path
from tests.lint_paths_support import write_slopgate_toml


def test_load_config_ignores_tests_quality_baselines_without_toml_override(
    tmp_path: Path,
) -> None:
    quality_dir = tmp_path / "tests" / "quality"
    quality_dir.mkdir(parents=True)
    (quality_dir / "baselines.json").write_text(
        '{"schema_version": 1, "bool_equality_max": 2}',
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    set_config(cfg)

    assert (cfg.baseline_path, baseline_path()) == (None, tmp_path / "baselines.json")


def test_load_config_honors_paths_baseline_path(tmp_path: Path) -> None:
    write_slopgate_toml(tmp_path, '[paths]\nbaseline_path = "custom/baseline.json"\n')

    cfg = load_config(tmp_path)
    set_config(cfg)

    expected = tmp_path / "custom" / "baseline.json"
    assert (cfg.baseline_path, baseline_path()) == (expected, expected)


def test_resolve_baseline_path_supports_absolute_paths(tmp_path: Path) -> None:
    absolute = tmp_path / "elsewhere" / "baseline.json"
    absolute.parent.mkdir(parents=True)
    write_slopgate_toml(
        tmp_path,
        f'[paths]\nbaseline_path = "{absolute.as_posix()}"\n',
    )

    assert resolve_baseline_path(tmp_path) == absolute.resolve()
