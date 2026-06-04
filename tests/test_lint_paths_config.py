from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.lint._config import load_config, reset_config, set_config
from slopgate.lint._helpers import find_source_files, find_test_files


@pytest.fixture(autouse=True)
def _reset_lint_config() -> None:
    yield
    reset_config()


def test_load_config_honors_paths_src_list(tmp_path: Path) -> None:
    lib_dir = tmp_path / "lib"
    extra_dir = tmp_path / "automation"
    _ = lib_dir.mkdir()
    _ = extra_dir.mkdir()
    _ = (lib_dir / "main.py").write_text("x = 1\n", encoding="utf-8")
    _ = (extra_dir / "job.py").write_text("y = 2\n", encoding="utf-8")
    _ = (tmp_path / "slopgate.toml").write_text(
        '[paths]\nsrc = ["lib", "automation"]\ntests = "tests"\n',
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    set_config(cfg)

    assert cfg.src_roots == (lib_dir.resolve(), extra_dir.resolve())
    assert {path.name for path in find_source_files()} == {"main.py", "job.py"}


def test_load_config_honors_paths_src_string(tmp_path: Path) -> None:
    custom = tmp_path / "pkg"
    _ = custom.mkdir()
    _ = (custom / "mod.py").write_text("x = 1\n", encoding="utf-8")
    _ = (tmp_path / "slopgate.toml").write_text(
        '[paths]\nsrc = "pkg"\n',
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    set_config(cfg)

    assert cfg.src_roots == (custom.resolve(),)
    assert [path.name for path in find_source_files()] == ["mod.py"]


def test_load_config_honors_paths_exclude_dirs(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    vendor = src_dir / "vendor"
    _ = vendor.mkdir(parents=True)
    _ = (vendor / "legacy.py").write_text("x = 1\n", encoding="utf-8")
    _ = (src_dir / "app.py").write_text("y = 2\n", encoding="utf-8")
    _ = (tmp_path / "slopgate.toml").write_text(
        '[paths]\nsrc = "src"\nexclude_dirs = ["vendor"]\n',
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    set_config(cfg)

    assert "vendor" in cfg.exclude_dirs
    assert {path.name for path in find_source_files()} == {"app.py"}


def test_load_config_honors_multiple_test_roots(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    support_dir = tmp_path / "test_support"
    _ = tests_dir.mkdir()
    _ = support_dir.mkdir()
    _ = (tests_dir / "test_app.py").write_text("def test_ok() -> None: pass\n", encoding="utf-8")
    _ = (support_dir / "test_helpers.py").write_text(
        "def test_helper() -> None: pass\n",
        encoding="utf-8",
    )
    _ = (tmp_path / "slopgate.toml").write_text(
        '[paths]\nsrc = "src"\ntests = ["tests", "test_support"]\n',
        encoding="utf-8",
    )

    cfg = load_config(tmp_path)
    set_config(cfg)

    assert cfg.test_roots == (tests_dir.resolve(), support_dir.resolve())
    assert {path.parent.name for path in find_test_files()} == {"tests", "test_support"}
