from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from slopgate.cli import repair
from slopgate.state import HookStateStore, RepairRequiredPayload
from tests.repair_cli.constants import GENERATION_ONE, GENERATION_TWO, REPAIR_PATH
from tests.repair_cli.support import ScopedLintCapture


def test_repair_verify_lints_recorded_paths_and_rule_ids(
    tmp_path: Path,
    recorded_lint_capture: tuple[
        ScopedLintCapture,
        list[tuple[Path, tuple[str, ...], tuple[str, ...]]],
    ],
) -> None:
    capture, expected = recorded_lint_capture

    result = repair.cmd_repair_verify(
        argparse.Namespace(cwd=str(tmp_path), generation=GENERATION_ONE)
    )

    assert result == 0, "matching generation should verify and clear"
    assert capture.calls == expected, "verification must lint recorded paths and rules"


def test_repair_verify_generation_mismatch_skips_lint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    marked_repair_store: HookStateStore,
) -> None:
    capture = ScopedLintCapture()
    monkeypatch.setattr(repair, "_run_scoped_lint", capture)

    result = repair.cmd_repair_verify(
        argparse.Namespace(cwd=str(tmp_path), generation=GENERATION_TWO)
    )
    remaining = marked_repair_store.get_repair_required()

    assert result == 1, "generation mismatch must fail closed"
    assert capture.calls == [], "generation mismatch must not start a scoped lint"
    assert json.loads(capsys.readouterr().out) == {"status": "generation_mismatch"}, (
        "generation mismatch must report status without clearing"
    )
    assert remaining is not None, "generation mismatch must retain REPAIR_REQUIRED"
    assert remaining["generation"] == GENERATION_ONE, (
        "generation mismatch must keep the armed generation"
    )


def test_repair_verify_dirty_scoped_lint_retains_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    marked_repair_store: HookStateStore,
) -> None:
    monkeypatch.setattr(repair, "_run_scoped_lint", ScopedLintCapture(returncode=1))

    result = repair.cmd_repair_verify(
        argparse.Namespace(cwd=str(tmp_path), generation=GENERATION_ONE)
    )
    remaining = marked_repair_store.get_repair_required()

    assert result == 1, "dirty scoped lint must fail closed"
    assert remaining is not None, "dirty scoped lint must retain REPAIR_REQUIRED"
    assert remaining["generation"] == GENERATION_ONE, (
        "dirty scoped lint must keep the armed generation"
    )


def test_repair_verify_does_not_clear_replaced_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    marked_repair_store: HookStateStore,
) -> None:
    payload = RepairRequiredPayload(
        session_id="session-one",
        call_id="call-one",
        rule_ids=["QUALITY-LINT-001"],
        paths=[REPAIR_PATH],
    )

    def replace_generation(
        _cwd: Path, _paths: list[str], _rule_ids: list[str]
    ) -> int:
        marked_repair_store.mark_repair_required(GENERATION_TWO, payload)
        return 0

    monkeypatch.setattr(repair, "_run_scoped_lint", replace_generation)

    result = repair.cmd_repair_verify(
        argparse.Namespace(cwd=str(tmp_path), generation=GENERATION_ONE)
    )
    required = marked_repair_store.get_repair_required()

    assert result == 1, "a replaced generation must fail closed"
    assert required is not None, "newer repair state must survive the stale verify"
    assert required["generation"] == GENERATION_TWO, (
        "verification must not clear a newer repair generation"
    )
