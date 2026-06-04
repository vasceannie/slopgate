"""Shared setup helpers for lint paths / freeze tests (keeps test bodies under eager-test limits)."""

from __future__ import annotations

import json
from pathlib import Path

from slopgate.lint._toml_overrides import apply_paths_overrides


def write_slopgate_toml(tmp_path: Path, body: str) -> None:
    (tmp_path / "slopgate.toml").write_text(body, encoding="utf-8")


def seed_paths_src_list_repo(tmp_path: Path) -> tuple[Path, Path]:
    lib_dir = tmp_path / "lib"
    extra_dir = tmp_path / "automation"
    lib_dir.mkdir()
    extra_dir.mkdir()
    (lib_dir / "main.py").write_text("x = 1\n", encoding="utf-8")
    (extra_dir / "job.py").write_text("y = 2\n", encoding="utf-8")
    write_slopgate_toml(
        tmp_path,
        '[paths]\nsrc = ["lib", "automation"]\ntests = "tests"\n',
    )
    return lib_dir, extra_dir


def seed_multi_test_roots_repo(tmp_path: Path) -> tuple[Path, Path]:
    tests_dir = tmp_path / "tests"
    support_dir = tmp_path / "test_support"
    tests_dir.mkdir()
    support_dir.mkdir()
    (tests_dir / "test_app.py").write_text(
        "def test_ok() -> None: pass\n",
        encoding="utf-8",
    )
    (support_dir / "test_helpers.py").write_text(
        "def test_helper() -> None: pass\n",
        encoding="utf-8",
    )
    write_slopgate_toml(
        tmp_path,
        '[paths]\nsrc = "src"\ntests = ["tests", "test_support"]\n',
    )
    return tests_dir, support_dir


def seed_freeze_repo(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "wide.py").write_text("x = 1\n" * 130, encoding="utf-8")
    write_slopgate_toml(tmp_path, '[paths]\nsrc = "src"\n')
    (tmp_path / "baselines.json").write_text(
        '{"schema_version": 1, "rules": {}}\n',
        encoding="utf-8",
    )


def freeze_rules_payload(tmp_path: Path) -> dict[str, object]:
    return json.loads((tmp_path / "baselines.json").read_text(encoding="utf-8"))


def apply_paths_overrides_for_scope(root: Path, scope: str) -> dict[str, object]:
    (root / "src").mkdir()
    write_slopgate_toml(
        root,
        f'[paths]\nsrc = "src"\n[scope]\ndefault = "{scope}"\n',
    )
    values: dict[str, object] = {}
    apply_paths_overrides(values, root)
    return values
