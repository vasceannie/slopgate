from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import pytest

from slopgate.adapters.opencode_projection import projector
from slopgate.adapters.opencode_projection import (
    OPENCODE_TOOL_CONTRACT_VERSION,
    ProjectionRequest,
    project_opencode_tool_input,
)
from slopgate._types import object_dict, object_list
from slopgate.adapters.opencode import OpenCodeAdapter
from slopgate.engine import evaluate_payload
from .support import enroll_repo, projection_for, raw_payload, write_source


def _nested_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    repo = enroll_repo(tmp_path, monkeypatch)
    directory = repo / "pkg"
    directory.mkdir()
    return repo, directory


def _projected_paths(projection: dict[str, object]) -> list[object]:
    return [object_dict(item).get("path") for item in object_list(projection["files"])]


def _add_file_patch(path: str) -> dict[str, object]:
    return {"patchText": f"*** Begin Patch\n*** Add File: {path}\n+y\n*** End Patch"}


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        pytest.param("src/a.py", "pkg/src/a.py", id="relative"),
        pytest.param("./a.py", "pkg/a.py", id="dot-relative"),
        pytest.param("../top.py", "top.py", id="parent-inside-repo"),
    ],
)
def test_relative_write_resolves_against_session_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, expected: str
) -> None:
    _repo, directory = _nested_session(tmp_path, monkeypatch)

    projection = projection_for(
        directory, "write", {"path": target, "content": "VALUE = 1\n"}
    )

    assert projection["status"] == "projected", "in-repo targets must project"
    assert _projected_paths(projection) == [expected], (
        "the checked path must be the file the host writes"
    )


def test_relative_edit_reads_the_file_under_session_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, directory = _nested_session(tmp_path, monkeypatch)
    write_source(repo, "pkg/a.py", "VALUE = 1\n")
    write_source(repo, "a.py", "OTHER = 1\n")

    projection = projection_for(
        directory,
        "edit",
        {"path": "a.py", "oldString": "VALUE = 1", "newString": "VALUE = 2"},
    )

    assert _projected_paths(projection) == ["pkg/a.py"], (
        "a relative edit must project the session file, not a repo-root namesake"
    )


def test_relative_patch_resolves_against_session_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo, directory = _nested_session(tmp_path, monkeypatch)

    projection = projection_for(directory, "patch", _add_file_patch("a.py"))

    assert _projected_paths(projection) == ["pkg/a.py"], (
        "patch sections must resolve like the host's FileAccess.resolvePath"
    )


def test_relative_patch_move_destination_resolves_against_session_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, directory = _nested_session(tmp_path, monkeypatch)
    write_source(repo, "pkg/a.py", "x\n")

    projection = projection_for(
        directory,
        "patch",
        {
            "patchText": "*** Begin Patch\n*** Update File: a.py\n"
            "*** Move to: ../b.py\n@@\n-x\n+y\n*** End Patch"
        },
    )

    assert _projected_paths(projection) == ["pkg/a.py", "b.py"], (
        "moves must resolve both endpoints from the session directory"
    )


def test_parent_traversal_out_of_repo_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo, directory = _nested_session(tmp_path, monkeypatch)

    projection = projection_for(
        directory, "write", {"path": "../../outside.py", "content": "x\n"}
    )

    assert projection["reason"] == "target_outside_root", (
        "the repo root, not the session directory, is the containment boundary"
    )


def _canonical_nested_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, object], Path]:
    _repo, directory = _nested_session(tmp_path, monkeypatch)
    canonical = OpenCodeAdapter().normalize_payload(
        raw_payload(directory, "write", {"path": "a.py", "content": "VALUE = 1\n"})
    )
    return object_dict(canonical["tool_input"]), directory.resolve() / "a.py"


def test_projected_edit_path_is_absolute_under_session_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool_input, written = _canonical_nested_write(tmp_path, monkeypatch)

    edit = object_dict(object_list(tool_input["edits"])[0])
    assert edit["file_path"] == str(written), (
        "rules resolve against both cwd and repo root, so only absolute is unambiguous"
    )


def test_top_level_path_matches_the_projected_edit_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool_input, written = _canonical_nested_write(tmp_path, monkeypatch)

    assert tool_input["path"] == str(written), (
        "targets dedupe by exact path, so one file must have one spelling"
    )


_HOME_TARGET_CASES = (
    pytest.param(
        "write", {"path": "~/.bashrc", "content": "x\n"}, id="write-tilde-slash"
    ),
    pytest.param("write", {"path": "~", "content": "x\n"}, id="write-bare-tilde"),
    pytest.param("patch", _add_file_patch("~/x"), id="patch-add"),
)


@pytest.mark.parametrize(("tool", "tool_input"), _HOME_TARGET_CASES)
def test_home_relative_target_outside_repo_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool: str,
    tool_input: dict[str, object],
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    projection = projection_for(repo, tool, tool_input)

    assert projection["reason"] == "target_outside_root", (
        "home targets must not be mistaken for an in-repo folder named ~"
    )


def test_home_relative_target_inside_repo_is_projected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    monkeypatch.setenv("HOME", str(repo))

    projection = projection_for(
        repo, "write", {"path": "~/a.py", "content": "VALUE = 1\n"}
    )

    assert _projected_paths(projection) == ["a.py"], (
        "tilde expansion must land on the repo file when home contains it"
    )


def test_tilde_user_form_stays_a_literal_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)

    projection = projection_for(
        repo, "write", {"path": "~other/a.py", "content": "VALUE = 1\n"}
    )

    assert _projected_paths(projection) == ["~other/a.py"], (
        "the host only expands ~ and ~/, so ~other stays a literal folder"
    )


def test_nested_cwd_projects_targets_from_enrolled_repo_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    nested_cwd = repo / "pkg"
    nested_cwd.mkdir()
    source = write_source(repo, "src/app.py", "VALUE = 1\n")

    projection = project_opencode_tool_input(
        ProjectionRequest(
            tool_name="edit",
            tool_input={
                "path": str(source),
                "oldString": "VALUE = 1",
                "newString": "VALUE = 2",
            },
            root=nested_cwd,
            contract_version=OPENCODE_TOOL_CONTRACT_VERSION,
        )
    )

    assert projection["status"] == "projected", (
        "nested cwd must still project targets inside the enrolled repository"
    )


def test_absolute_external_target_is_rejected_before_snapshot_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    external = tmp_path / "outside.py"
    external.write_text("VALUE = 1\n", encoding="utf-8")

    def fail_snapshot(_root: Path, _relative: str) -> NoReturn:
        raise AssertionError("outside targets must not reach snapshot I/O")

    monkeypatch.setattr(projector, "read_snapshot", fail_snapshot)
    projection = project_opencode_tool_input(
        ProjectionRequest(
            tool_name="edit",
            tool_input={
                "path": str(external),
                "oldString": "VALUE = 1",
                "newString": "VALUE = 2",
            },
            root=repo,
            contract_version=OPENCODE_TOOL_CONTRACT_VERSION,
        )
    )

    assert projection["status"] == "invalid", "external targets must be invalid"
    assert projection["reason"] == "target_outside_root", (
        "external targets must report their scope failure"
    )
    assert projection["files"] == [], "external targets must expose no files"


def test_external_projection_denial_is_scoped_without_path_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    external = tmp_path / "outside.py"
    result = evaluate_payload(
        raw_payload(
            repo,
            "edit",
            {
                "path": str(external),
                "oldString": "VALUE = 1",
                "newString": "VALUE = 2",
            },
        ),
        platform="opencode",
    )

    assert result.output is not None, "external mutations must receive a denial"
    reason = str(result.output.get("reason"))
    assert "outside the managed repository" in reason, (
        "scope denials must explain the managed-repository boundary"
    )
    assert str(external) not in reason, "scope denials must not leak target paths"
    assert str(repo) not in reason, "scope denials must not leak root paths"
    finding = next(
        finding for finding in result.findings if finding.rule_id == "OC-PROJECTION-001"
    )
    assert "path" not in finding.metadata, (
        "external targets must not populate repository-relative finding metadata"
    )
