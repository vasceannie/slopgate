from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from slopgate._types import ObjectDict
from slopgate.cli import repair
from slopgate.state import HookStateStore, RepairRequiredPayload, RepairTarget
from tests.repair_cli.constants import (
    CLEAN_SOURCE,
    COMPLEXITY_RULE,
    GENERATION_ONE,
    GENERATION_TWO,
    REPAIR_PATH,
    REPAIR_REQUIRED_STATUS,
    REPAIR_STATE_INVALID_STATUS,
)
from tests.repair_cli.support import (
    ScopedLintCapture,
    WritableRepairStateStore,
    legacy_repair_record,
)


def test_repair_verify_lints_recorded_paths_and_rule_ids(
    tmp_path: Path,
    recorded_lint_capture: tuple[
        ScopedLintCapture,
        list[tuple[Path, tuple[ObjectDict, ...]]],
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
    monkeypatch.setattr("slopgate.cli.repair._commands._run_scoped_lint", capture)

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
    monkeypatch.setattr(
        "slopgate.cli.repair._commands._run_scoped_lint",
        ScopedLintCapture(returncode=1),
    )

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
        worktree=str(tmp_path.resolve()),
        targets=[
            RepairTarget("QUALITY-LINT-001", REPAIR_PATH, REPAIR_PATH, None, None)
        ],
    )

    def replace_generation(_cwd: Path, _targets: list[ObjectDict]) -> int:
        marked_repair_store.mark_repair_required(GENERATION_TWO, payload)
        return 0

    monkeypatch.setattr(
        "slopgate.cli.repair._commands._run_scoped_lint", replace_generation
    )

    result = repair.cmd_repair_verify(
        argparse.Namespace(cwd=str(tmp_path), generation=GENERATION_ONE)
    )
    required = marked_repair_store.get_repair_required()

    assert result == 1, "a replaced generation must fail closed"
    assert required is not None, "newer repair state must survive the stale verify"
    assert required["generation"] == GENERATION_TWO, (
        "verification must not clear a newer repair generation"
    )


def _status_of_recorded_generation(
    store: WritableRepairStateStore,
    project: Path,
    record: ObjectDict,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, ObjectDict]:
    store.save_repair_record(record)
    result = repair.cmd_repair_status(argparse.Namespace(cwd=str(project)))
    return result, json.loads(capsys.readouterr().out)


def _verify_recorded_generation(
    store: WritableRepairStateStore,
    project: Path,
    record: ObjectDict,
) -> tuple[int, ObjectDict | None]:
    store.save_repair_record(record)
    result = repair.cmd_repair_verify(
        argparse.Namespace(cwd=str(project), generation=GENERATION_ONE)
    )
    return result, store.get_repair_required()


def _legacy_record(project: Path, paths: list[str]) -> ObjectDict:
    """Legacy record whose paths are normalized the way the old writer stored them."""
    return legacy_repair_record(
        generation=GENERATION_ONE,
        paths=[str(project / path) for path in paths],
        rule_ids=[COMPLEXITY_RULE],
    )


def _armed_generation(remaining: ObjectDict | None) -> str | None:
    value = None if remaining is None else remaining.get("generation")
    return value if isinstance(value, str) else None


def _unresolvable_legacy_path(project: Path, case: str) -> str:
    if case == "missing-in-root":
        return str(project / "src" / "gone.py")
    outside = project.parent / "legacy-outside.py"
    outside.write_text(CLEAN_SOURCE, encoding="utf-8")
    return str(outside)


def test_repair_status_accepts_legacy_generation_without_worktree_field(
    repair_project: Path,
    writable_repair_store: WritableRepairStateStore,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result, status = _status_of_recorded_generation(
        writable_repair_store,
        repair_project,
        _legacy_record(repair_project, [REPAIR_PATH]),
        capsys,
    )

    assert result == 0, "a generation recorded without worktree provenance must load"
    assert status["status"] == REPAIR_REQUIRED_STATUS, (
        "a legacy generation must keep the repair gate armed"
    )
    assert status["generation"] == GENERATION_ONE, (
        "a legacy generation must still report its recorded generation"
    )


def test_repair_verify_clears_legacy_generation_without_worktree_field(
    repair_project: Path,
    writable_repair_store: WritableRepairStateStore,
) -> None:
    result, remaining = _verify_recorded_generation(
        writable_repair_store,
        repair_project,
        _legacy_record(repair_project, [REPAIR_PATH]),
    )

    assert result == 0, "clean recorded legacy paths must verify and clear"
    assert remaining is None, (
        "upgrading must not leave a legacy generation permanently unclearable"
    )


@pytest.mark.parametrize("case", ["missing-in-root", "outside-worktree"])
def test_repair_verify_retains_legacy_generation_when_paths_do_not_resolve(
    repair_project: Path,
    writable_repair_store: WritableRepairStateStore,
    case: str,
) -> None:
    recorded = _unresolvable_legacy_path(repair_project, case)
    result, remaining = _verify_recorded_generation(
        writable_repair_store,
        repair_project,
        _legacy_record(repair_project, [recorded]),
    )

    assert result == 1, f"{case} legacy path must fail closed"
    assert _armed_generation(remaining) == GENERATION_ONE, (
        f"{case} legacy path must keep the armed generation"
    )


def test_repair_verify_retains_legacy_generation_without_recorded_paths(
    repair_project: Path,
    writable_repair_store: WritableRepairStateStore,
) -> None:
    result, remaining = _verify_recorded_generation(
        writable_repair_store, repair_project, _legacy_record(repair_project, [])
    )

    assert result == 1, "a legacy generation without recorded paths must fail closed"
    assert _armed_generation(remaining) == GENERATION_ONE, (
        "a legacy generation with nothing to verify must keep the armed generation"
    )


@pytest.mark.parametrize(
    "worktree",
    [
        pytest.param(None, id="null-field"),
        pytest.param(7, id="non-string-field"),
        pytest.param("other-worktree", id="foreign-worktree"),
    ],
)
def test_repair_status_rejects_recorded_generation_without_matching_worktree(
    repair_project: Path,
    writable_repair_store: WritableRepairStateStore,
    capsys: pytest.CaptureFixture[str],
    worktree: object,
) -> None:
    record = _legacy_record(repair_project, [REPAIR_PATH])
    record["worktree"] = worktree

    result, status = _status_of_recorded_generation(
        writable_repair_store, repair_project, record, capsys
    )

    assert result == 2, "a present but unusable worktree field must fail closed"
    assert status["status"] == REPAIR_STATE_INVALID_STATUS, (
        "an unusable worktree field must report invalid repair state"
    )
