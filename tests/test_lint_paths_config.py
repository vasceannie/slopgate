from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given
from hypothesis import strategies as st

from slopgate.lint._config import load_config, set_config
from slopgate.lint._helpers import find_source_files, find_test_files
from slopgate.lint._toml_overrides import apply_paths_overrides, resolve_root_paths
from tests.lint_paths_support import (
    apply_paths_overrides_for_scope,
    seed_multi_test_roots_repo,
    seed_paths_src_list_repo,
    write_slopgate_toml,
)


def test_resolve_root_paths_honors_src_array(tmp_path: Path) -> None:
    lib_dir = tmp_path / "lib"
    extra_dir = tmp_path / "automation"
    lib_dir.mkdir()
    extra_dir.mkdir()
    write_slopgate_toml(tmp_path, '[paths]\nsrc = ["lib", "automation"]\n')

    roots = resolve_root_paths(tmp_path, "src", "src")

    assert roots == (lib_dir.resolve(), extra_dir.resolve())


def test_apply_paths_overrides_sets_roots_and_scope(tmp_path: Path) -> None:
    src_dir = tmp_path / "pkg"
    tests_dir = tmp_path / "spec"
    src_dir.mkdir()
    tests_dir.mkdir()
    write_slopgate_toml(
        tmp_path,
        '[paths]\nsrc = "pkg"\ntests = "spec"\n[scope]\ndefault = "strict"\n',
    )

    values: dict[str, object] = {}
    apply_paths_overrides(values, tmp_path)

    src_resolved = src_dir.resolve()
    tests_resolved = tests_dir.resolve()
    assert values == {
        "src_roots": (src_resolved,),
        "test_roots": (tests_resolved,),
        "src_root": src_resolved,
        "tests_root": tests_resolved,
        "default_scope": "strict",
    }


@given(scope=st.sampled_from(["strict", "relaxed"]))
def test_apply_paths_overrides_default_scope_property(scope: str) -> None:
    with TemporaryDirectory() as raw:
        values = apply_paths_overrides_for_scope(Path(raw), scope)
    assert values.get("default_scope") == scope


def test_load_config_honors_paths_src_list(tmp_path: Path) -> None:
    lib_dir, extra_dir = seed_paths_src_list_repo(tmp_path)
    cfg = load_config(tmp_path)
    set_config(cfg)
    assert (cfg.src_roots, {path.name for path in find_source_files()}) == (
        (lib_dir.resolve(), extra_dir.resolve()),
        {"main.py", "job.py"},
    )


def test_load_config_honors_paths_src_string(tmp_path: Path) -> None:
    custom = tmp_path / "pkg"
    custom.mkdir()
    (custom / "mod.py").write_text("x = 1\n", encoding="utf-8")
    write_slopgate_toml(tmp_path, '[paths]\nsrc = "pkg"\n')

    cfg = load_config(tmp_path)
    set_config(cfg)

    assert (cfg.src_roots, [path.name for path in find_source_files()]) == (
        (custom.resolve(),),
        ["mod.py"],
    )


def test_load_config_honors_paths_exclude_dirs(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    vendor = src_dir / "vendor"
    vendor.mkdir(parents=True)
    (vendor / "legacy.py").write_text("x = 1\n", encoding="utf-8")
    (src_dir / "app.py").write_text("y = 2\n", encoding="utf-8")
    write_slopgate_toml(
        tmp_path,
        '[paths]\nsrc = "src"\nexclude_dirs = ["vendor"]\n',
    )

    cfg = load_config(tmp_path)
    set_config(cfg)

    assert ("vendor" in cfg.exclude_dirs, {path.name for path in find_source_files()}) == (
        True,
        {"app.py"},
    )


def test_load_config_honors_multiple_test_roots(tmp_path: Path) -> None:
    tests_dir, support_dir = seed_multi_test_roots_repo(tmp_path)
    cfg = load_config(tmp_path)
    set_config(cfg)
    assert (cfg.test_roots, {path.parent.name for path in find_test_files()}) == (
        (tests_dir.resolve(), support_dir.resolve()),
        {"tests", "test_support"},
    )
