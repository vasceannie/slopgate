"""Indexed uncommitted files skip parse when content already matches the store."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import TypedDict

import pytest

from slopgate.lint._collectors import CollectorRunOptions, run_all_collectors
from slopgate.lint._config import load_config, reset_config, set_config
from tests.lint_paths_support import run_test_git

LONG_LINE = "value = " + " + ".join(["1"] * 80) + "\n"


class _IndexedParseResult(TypedDict):
    calls: list[str]
    hits: int


def _seed_committed_source(root: Path) -> Path:
    (root / "slopgate.toml").write_text("[slopgate]\nenabled = true\n", encoding="utf-8")
    set_config(load_config(root))
    source = root / "src/pkg/one.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def ok() -> int:\n    return 1\n", encoding="utf-8")
    run_test_git(root, "init", "-b", "main")
    run_test_git(root, "add", "slopgate.toml", "src/pkg/one.py")
    run_test_git(root, "commit", "-m", "seed", test_identity=True)
    return source


def _indexed_uncommitted_parse_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> _IndexedParseResult:
    from slopgate.lint._helpers.parsing import parse_file_attempt

    source = _seed_committed_source(tmp_path)
    source.write_text(LONG_LINE, encoding="utf-8")
    options = CollectorRunOptions(persist_index=True, use_index=True)
    dict(run_all_collectors([source], [], options))
    calls: list[str] = []

    def tracked(path: Path):
        calls.append(path.name)
        return parse_file_attempt(path)

    monkeypatch.setattr("slopgate.lint._helpers.parsing.parse_file_attempt", tracked)
    hits = dict(run_all_collectors([source], [], options))
    reset_config()
    return {"calls": calls, "hits": len(hits["long-line"])}


def test_indexed_uncommitted_files_skip_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _indexed_uncommitted_parse_contract(tmp_path, monkeypatch) == {
        "calls": [],
        "hits": 1,
    }


def _preserved_stat_change_contract(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    fail_git_paths: bool = False,
) -> list[str]:
    from slopgate.lint._helpers.parsing import parse_file_attempt

    source = _seed_committed_source(root)
    options = CollectorRunOptions(persist_index=True, use_index=True)
    dict(run_all_collectors([source], [], options))
    original_stat = source.stat()
    source.write_text("def ok() -> int:\n    return 2\n", encoding="utf-8")
    os.utime(
        source,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )
    calls: list[str] = []

    if fail_git_paths:

        def failed_git_output(
            args: list[str], *, cwd: Path | None = None, timeout: int = 3
        ) -> str | None:
            del cwd, timeout
            if "rev-parse" in args:
                return "true"
            return None

        monkeypatch.setattr(
            "slopgate.lint.project_index.dirty.git_output",
            failed_git_output,
        )

    def tracked(path: Path):
        calls.append(path.name)
        return parse_file_attempt(path)

    monkeypatch.setattr("slopgate.lint._helpers.parsing.parse_file_attempt", tracked)
    dict(run_all_collectors([source], [], options))
    reset_config()
    return calls


def test_indexed_git_dirty_file_rechecks_content_when_stat_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _preserved_stat_change_contract(tmp_path, monkeypatch) == ["one.py"]


def test_git_path_failure_rechecks_preserved_stat_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _preserved_stat_change_contract(
        tmp_path,
        monkeypatch,
        fail_git_paths=True,
    ) == ["one.py"]


def _clean_warm_stat_contract(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, int]:
    source = _seed_committed_source(root)
    options = CollectorRunOptions(persist_index=True, use_index=True)
    first = dict(run_all_collectors([source], [], options))

    def unexpected_content_check(_path: Path, _row: sqlite3.Row) -> bool:
        raise AssertionError("clean stat-matched files should not be reread")

    monkeypatch.setattr(
        "slopgate.lint.project_index.peek._row_content_matches",
        unexpected_content_check,
    )
    second = dict(run_all_collectors([source], [], options))
    reset_config()
    return len(first["long-line"]), len(second["long-line"])


def test_clean_warm_index_skips_content_hashing_when_stat_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _clean_warm_stat_contract(tmp_path, monkeypatch) == (0, 0)


def _tracked_sqlite_cache_contract(root: Path) -> tuple[int, int]:
    source = _seed_committed_source(root)
    source.write_text(LONG_LINE, encoding="utf-8")
    run_test_git(root, "add", "src/pkg/one.py")
    run_test_git(root, "commit", "-m", "add violation", test_identity=True)
    options = CollectorRunOptions(persist_index=True, use_index=True)
    initial = dict(run_all_collectors([source], [], options))
    cache_path = root / ".slopgate/cache/lint-index.sqlite"
    with sqlite3.connect(cache_path) as connection:
        connection.execute("DELETE FROM file_violations")
        connection.commit()
    run_test_git(root, "add", "-f", ".slopgate/cache/lint-index.sqlite")

    refreshed = dict(run_all_collectors([source], [], options))
    reset_config()
    return len(initial["long-line"]), len(refreshed["long-line"])


def test_tracked_sqlite_cache_cannot_suppress_current_violation(tmp_path: Path) -> None:
    assert _tracked_sqlite_cache_contract(tmp_path) == (1, 1)
