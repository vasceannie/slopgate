"""Shared helpers for OpenCode projection adapter tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import strategies

from slopgate._types import object_dict
from slopgate.adapters.opencode import OpenCodeAdapter
from slopgate.engine import evaluate_payload
from slopgate.models import EngineResult

OPENCODE_TOOL_CONTRACT_VERSION = "slopgate-opencode-projection-v1"
UNKNOWN_TOOL_INPUTS = strategies.dictionaries(
    strategies.text(min_size=1),
    strategies.one_of(
        strategies.none(),
        strategies.booleans(),
        strategies.integers(),
        strategies.text(),
    ),
    max_size=8,
)


def raw_payload(
    repo: Path, tool_name: str, tool_input: dict[str, object]
) -> dict[str, object]:
    return {
        "hook_event_name": "tool.execute.before",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "cwd": str(repo),
        "worktree": str(repo),
        "session_id": "projection-session",
        "call_id": "projection-call",
        "opencode_tool_contract_version": OPENCODE_TOOL_CONTRACT_VERSION,
    }


def projection_meta(canonical: dict[str, object]) -> dict[str, object]:
    tool_input = object_dict(canonical.get("tool_input"))
    return object_dict(tool_input.get("_slopgate_projection"))


def projection_for(
    repo: Path, tool_name: str, tool_input: dict[str, object]
) -> dict[str, object]:
    canonical = OpenCodeAdapter().normalize_payload(
        raw_payload(repo, tool_name, tool_input)
    )
    return projection_meta(canonical)


def write_source(repo: Path, relative: str, content: str) -> Path:
    source = repo / relative
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8")
    return source


def enroll_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "slopgate.toml").write_text("[slopgate]\nenabled = true\n", encoding="utf-8")
    monkeypatch.setenv("SLOPGATE_ROOT", str(tmp_path / "slopgate-root"))
    return repo


def plant_stale_symlink_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    repo = enroll_repo(tmp_path, monkeypatch)
    outside = tmp_path / "outside.txt"
    outside.write_text("VALUE = 1\n", encoding="utf-8")
    linked = repo / "src" / "app.py"
    linked.parent.mkdir()
    linked.symlink_to(outside)
    return repo, outside


def evaluate_stale_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[EngineResult, dict[str, object], Path]:
    repo, outside = plant_stale_symlink_repo(tmp_path, monkeypatch)
    payload = raw_payload(
        repo,
        "edit",
        {"filePath": "src/app.py", "oldString": "VALUE = 1", "newString": "VALUE = 2"},
    )
    result = evaluate_payload(payload, platform="opencode")
    projection = projection_meta(OpenCodeAdapter().normalize_payload(payload))
    return result, projection, outside


def evaluate_before(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    tool_input: dict[str, object],
    *,
    contract_version: str = OPENCODE_TOOL_CONTRACT_VERSION,
) -> tuple[EngineResult, dict[str, object]]:
    repo = enroll_repo(tmp_path, monkeypatch)
    payload = raw_payload(repo, tool_name, tool_input)
    payload["opencode_tool_contract_version"] = contract_version
    return evaluate_payload(payload, platform="opencode"), projection_meta(
        OpenCodeAdapter().normalize_payload(payload)
    )
