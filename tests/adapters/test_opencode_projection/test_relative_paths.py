"""Relative OpenCode paths must receive the same policy as absolute ones.

Models choose the path form, so a bare filename must not change enforcement.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from slopgate._types import ObjectDict, object_dict
from slopgate.context import build_context
from slopgate.engine import evaluate_payload
from slopgate.models import EngineResult
from .support import enroll_repo, raw_payload, write_source

_WEAK_TEST = "def test_weak() -> None:\n    assert str(1) is not None\n"
_SYNTAX_ERROR = "def broken(:\n"
_ORIGINAL = "VALUE = 1\n"
_PATH_SCOPED_RULE = "PY-TYPE-001"
_RELATIVE_WRITES = [
    pytest.param(("", "a.py"), id="bare-at-root"),
    pytest.param(("", "./a.py"), id="dot-at-root"),
    pytest.param(("pkg", "a.py"), id="bare-in-subdirectory"),
    pytest.param(("pkg", "../a.py"), id="parent-from-subdirectory"),
]
_PATH_FORMS = [
    pytest.param(False, id="relative"),
    pytest.param(True, id="absolute"),
]


def _evaluate_in_session(
    repo: Path, session: str, tool: str, tool_input: ObjectDict
) -> EngineResult:
    directory = repo / session
    directory.mkdir(exist_ok=True)
    payload = raw_payload(directory, tool, tool_input) | {"worktree": str(repo)}
    return evaluate_payload(payload, platform="opencode")


def _violating_content(load_fixture: Callable[[str], ObjectDict]) -> str:
    tool_input = object_dict(load_fixture("pretool_python_any.json")["tool_input"])
    return str(tool_input["content"])


def _rule_ids(result: EngineResult) -> set[str]:
    return {finding.rule_id for finding in result.findings}


@pytest.mark.parametrize("session_and_target", _RELATIVE_WRITES)
def test_path_scoped_policy_applies_to_relative_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    load_fixture: Callable[[str], ObjectDict],
    session_and_target: tuple[str, str],
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    session, target = session_and_target

    result = _evaluate_in_session(
        repo,
        session,
        "write",
        {"path": target, "content": _violating_content(load_fixture)},
    )

    assert _PATH_SCOPED_RULE in _rule_ids(result), (
        "a relative path must not fall out of **/ scoped policy"
    )


def test_path_scoped_policy_applies_to_bare_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    load_fixture: Callable[[str], ObjectDict],
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    write_source(repo, "a.py", _ORIGINAL)

    result = _evaluate_in_session(
        repo,
        "",
        "edit",
        {
            "path": "a.py",
            "oldString": _ORIGINAL,
            "newString": _violating_content(load_fixture),
        },
    )

    assert _PATH_SCOPED_RULE in _rule_ids(result), (
        "a bare-path edit must be judged on its projected content"
    )


def test_path_scoped_policy_applies_to_bare_patch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    load_fixture: Callable[[str], ObjectDict],
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    added = "".join(
        f"+{line}\n" for line in _violating_content(load_fixture).splitlines()
    )

    result = _evaluate_in_session(
        repo,
        "",
        "patch",
        {"patchText": f"*** Begin Patch\n*** Add File: a.py\n{added}*** End Patch"},
    )

    assert _PATH_SCOPED_RULE in _rule_ids(result), (
        "a bare patch target must be judged on its projected content"
    )


def _report_weak_test_written_from_subdirectory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ObjectDict | None, Path]:
    repo = enroll_repo(tmp_path, monkeypatch)
    directory = repo / "pkg"
    directory.mkdir()
    source = write_source(repo, "tests/test_weak.py", _WEAK_TEST)
    payload = raw_payload(
        directory,
        "write",
        {"path": "../tests/test_weak.py", "content": _WEAK_TEST},
    ) | {
        "worktree": str(repo),
        "hook_event_name": "tool.execute.after",
        "execution_outcome": "returned",
    }
    evaluate_payload(payload, platform="opencode")
    state = build_context({"cwd": str(repo), "worktree": str(repo)}).state
    return state.get_repair_required(), source


def test_post_tool_lint_arms_repair_for_parent_relative_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    required, source = _report_weak_test_written_from_subdirectory(
        tmp_path, monkeypatch
    )

    assert required is not None, "post-tool lint must see the file the host wrote"
    assert required["paths"] == [str(source.resolve())], (
        "repair must target the written file, not a path joined to the repo root"
    )


@pytest.mark.parametrize("absolute", _PATH_FORMS)
def test_one_write_is_evaluated_once_for_either_path_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, absolute: bool
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    target = str(repo / "a.py") if absolute else "a.py"

    result = _evaluate_in_session(
        repo, "", "write", {"path": target, "content": _SYNTAX_ERROR}
    )

    syntax_findings = [
        finding for finding in result.findings if finding.rule_id == "PY-AST-001"
    ]
    assert len(syntax_findings) == 1, (
        "the top-level path and projected edit must not spell one file two ways"
    )
