"""Operator escape hatch for a pending repair generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from slopgate._types import ObjectDict
from slopgate.cli import repair
from slopgate.state import HookStateStore, RepairRequiredPayload
from tests.repair_cli.constants import (
    GENERATION_ONE,
    GENERATION_TWO,
    REPAIR_REQUIRED_STATUS,
    REPAIR_STATE_INVALID_STATUS,
)
from tests.repair_cli.support import WritableRepairStateStore


def _clear_generation(
    project: Path,
    generation: str,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, ObjectDict]:
    result = repair.cmd_repair_clear(
        argparse.Namespace(cwd=str(project), generation=generation)
    )
    return result, json.loads(capsys.readouterr().out)


def test_repair_clear_releases_the_matching_generation(
    tmp_path: Path,
    repair_store: HookStateStore,
    repair_payload: RepairRequiredPayload,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repair_store.mark_repair_required(GENERATION_ONE, repair_payload)

    result, status = _clear_generation(tmp_path, GENERATION_ONE, capsys)

    assert result == 0, "the operator escape hatch must release a matching generation"
    assert status == {"status": "cleared", "generation": GENERATION_ONE}, (
        "clearing must report the generation it released"
    )
    assert repair_store.get_repair_required() is None, (
        "a cleared generation must not stay armed"
    )


def test_repair_clear_rejects_a_stale_generation(
    tmp_path: Path,
    repair_store: HookStateStore,
    repair_payload: RepairRequiredPayload,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repair_store.mark_repair_required(GENERATION_ONE, repair_payload)

    result, status = _clear_generation(tmp_path, GENERATION_TWO, capsys)
    remaining = repair_store.get_repair_required() or {}

    assert result == 1, "a stale generation must not release the pending lock"
    assert status == {"status": "generation_mismatch"}, (
        "a stale generation must report the mismatch instead of clearing"
    )
    assert remaining.get("generation") == GENERATION_ONE, (
        "the armed generation must survive a stale clear"
    )


def test_repair_clear_is_a_no_op_when_nothing_is_pending(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result, status = _clear_generation(tmp_path, GENERATION_ONE, capsys)

    assert result == 0, "clearing with no pending generation must succeed as a no-op"
    assert status == {"status": "clean"}, (
        "clearing with nothing pending must report clean state"
    )


def test_repair_clear_rejects_a_generation_from_another_worktree(
    repair_project: Path,
    writable_repair_store: WritableRepairStateStore,
    capsys: pytest.CaptureFixture[str],
) -> None:
    writable_repair_store.save_repair_record(
        {
            "status": REPAIR_REQUIRED_STATUS,
            "generation": GENERATION_ONE,
            "worktree": str(repair_project.parent / "other-worktree"),
            "targets": [],
        }
    )

    result, status = _clear_generation(repair_project, GENERATION_ONE, capsys)

    assert result == 2, "another worktree's generation must not be clearable"
    assert status["status"] == REPAIR_STATE_INVALID_STATUS, (
        "a foreign worktree field must report invalid repair state"
    )
