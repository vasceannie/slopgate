"""Contracts for all-scope inventory reuse of a ready enrolled index."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopgate.lint._config import load_config, reset_config, set_config
from slopgate.lint._helpers.discovery import find_source_files
from slopgate.lint.project_index.models import ProjectIndexRequest
from slopgate.lint.project_index.persist import build_persisted_index
from slopgate.lint.project_index.store import connect_index, mark_file_local_ready

GIT_TEST_USER_NAME = "Slopgate Tests"
GIT_TEST_USER_EMAIL = "slopgate-tests@example.invalid"


def _run_git(repo: Path, *args: str, test_identity: bool = False) -> None:
    command = ["git", "-C", str(repo)]
    if test_identity:
        command.extend(
            [
                "-c",
                f"user.name={GIT_TEST_USER_NAME}",
                "-c",
                f"user.email={GIT_TEST_USER_EMAIL}",
            ]
        )
    command.extend(args)
    subprocess.run(
        command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )


def _ready_indexed_repo(root: Path) -> tuple[Path, Path]:
    (root / "slopgate.toml").write_text("[slopgate]\nenabled = true\n", encoding="utf-8")
    source = root / "src/pkg/mod.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def ok() -> int:\n    return 1\n", encoding="utf-8")
    _run_git(root, "init", "-b", "main")
    _run_git(root, "add", "slopgate.toml", "src/pkg/mod.py")
    _run_git(root, "commit", "-m", "seed", test_identity=True)
    set_config(load_config(root))
    build_persisted_index(
        ProjectIndexRequest(
            root=root, src_files=(source,), test_files=(), persist=True, use_store=True
        )
    )
    connection = connect_index(root)
    mark_file_local_ready(connection)
    connection.commit()
    connection.close()
    extra = root / "src/pkg/extra.py"
    extra.write_text("x = 1\n", encoding="utf-8")
    return source, extra


def _indexed_inventory_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> set[str]:
    _ready_indexed_repo(tmp_path)

    def boom(*args: object, **kwargs: object) -> list[object]:
        raise AssertionError("find_source_files walked after index ready")

    monkeypatch.setattr("slopgate.lint._helpers.discovery.os.walk", boom)
    found = find_source_files()
    reset_config()
    return {path.name for path in found}


def test_find_source_files_uses_ready_index_and_untracked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _indexed_inventory_names(tmp_path, monkeypatch) == {"mod.py", "extra.py"}
