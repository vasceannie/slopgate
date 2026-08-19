"""Warm dirty lint check parses only changed files and keeps project-scope hits."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopgate.lint._collectors import CollectorRunOptions, run_all_collectors
from slopgate.lint._config import load_config, reset_config, set_config

GIT_TEST_USER_NAME = "Slopgate Tests"
GIT_TEST_USER_EMAIL = "slopgate-tests@example.invalid"
CLONE_FN = (
    "def shared() -> int:\n"
    "    left = 1\n"
    "    right = 2\n"
    "    mid = left + right\n"
    "    extra = mid + 1\n"
    "    return extra\n"
)
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


def _seed_clone_repo(root: Path) -> tuple[Path, Path, Path]:
    (root / "slopgate.toml").write_text("[slopgate]\nenabled = true\n", encoding="utf-8")
    set_config(load_config(root))
    first = root / "src/pkg/one.py"
    second = root / "src/pkg/two.py"
    third = root / "src/pkg/three.py"
    first.parent.mkdir(parents=True, exist_ok=True)
    first.write_text(CLONE_FN, encoding="utf-8")
    second.write_text(CLONE_FN, encoding="utf-8")
    third.write_text(LONG_LINE, encoding="utf-8")
    _run_git(root, "init", "-b", "main")
    _run_git(root, "add", "slopgate.toml", "src/pkg/one.py", "src/pkg/two.py", "src/pkg/three.py")
    _run_git(root, "commit", "-m", "seed", test_identity=True)
    return first, second, third


def _warm_dirty_parse_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    from slopgate.lint._helpers.parsing import parse_file_attempt

    first, second, third = _seed_clone_repo(tmp_path)
    options = CollectorRunOptions(persist_index=True, use_index=True)
    cold = dict(run_all_collectors([first, second, third], [], options))
    third.write_text("def ok() -> int:\n    return 1\n", encoding="utf-8")
    _run_git(tmp_path, "add", "src/pkg/three.py")
    _run_git(tmp_path, "commit", "-m", "trim three", test_identity=True)
    calls: list[str] = []

    def tracked(path: Path):
        calls.append(path.name)
        return parse_file_attempt(path)

    monkeypatch.setattr("slopgate.lint._helpers.parsing.parse_file_attempt", tracked)
    warm = dict(run_all_collectors([first, second, third], [], options))
    reset_config()
    return {
        "calls": calls,
        "cold_clones": len(cold["semantic-clone"]),
        "warm_clones": len(warm["semantic-clone"]),
        "warm_long": len(warm["long-line"]),
    }


def test_warm_dirty_parses_only_changed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _warm_dirty_parse_contract(tmp_path, monkeypatch) == {
        "calls": ["three.py"],
        "cold_clones": 2,
        "warm_clones": 2,
        "warm_long": 0,
    }


def _dirty_constant_reuse_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    from slopgate.lint._helpers.profile import LintProfile
    from slopgate.quality.constant_index import reset_session_constant_index

    first, second, third = _seed_clone_repo(tmp_path)
    options = CollectorRunOptions(persist_index=True, use_index=True)
    dict(run_all_collectors([first, second, third], [], options))
    third.write_text("def ok() -> int:\n    return 1\n", encoding="utf-8")
    _run_git(tmp_path, "add", "src/pkg/three.py")
    _run_git(tmp_path, "commit", "-m", "trim three", test_identity=True)
    builds: list[int] = []

    def tracked(*_args: object, **_kwargs: object):
        builds.append(1)
        raise AssertionError("dirty run should reuse the session constant index")

    monkeypatch.setattr(
        "slopgate.quality.constant_index.build_project_constant_index", tracked
    )
    profile = LintProfile()
    dict(
        run_all_collectors(
            [first, second, third],
            [],
            CollectorRunOptions(persist_index=True, use_index=True, profile=profile),
        )
    )
    reset_config()
    reset_session_constant_index()
    return {"builds": builds, "persist": "persist" in profile.phases}


def test_dirty_run_reuses_session_constant_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _dirty_constant_reuse_contract(tmp_path, monkeypatch) == {
        "builds": [],
        "persist": True,
    }
