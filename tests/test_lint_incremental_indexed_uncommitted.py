"""Indexed uncommitted files skip parse when content already matches the store."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopgate.lint._collectors import CollectorRunOptions, run_all_collectors
from slopgate.lint._config import load_config, reset_config, set_config

GIT_TEST_USER_NAME = "Slopgate Tests"
GIT_TEST_USER_EMAIL = "slopgate-tests@example.invalid"
LONG_LINE = "value = " + " + ".join(["1"] * 80) + "\n"


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


def _seed_committed_source(root: Path) -> Path:
    (root / "slopgate.toml").write_text("[slopgate]\nenabled = true\n", encoding="utf-8")
    set_config(load_config(root))
    source = root / "src/pkg/one.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def ok() -> int:\n    return 1\n", encoding="utf-8")
    _run_git(root, "init", "-b", "main")
    _run_git(root, "add", "slopgate.toml", "src/pkg/one.py")
    _run_git(root, "commit", "-m", "seed", test_identity=True)
    return source


def _indexed_uncommitted_parse_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
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
