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
from slopgate.engine import evaluate_payload
from .support import enroll_repo, raw_payload, write_source


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
                "filePath": str(source),
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
                "filePath": str(external),
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
                "filePath": str(external),
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
