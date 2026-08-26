from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from slopgate.cli import repair
from slopgate.cli.lint import cmd_lint
from slopgate.state import HookStateStore, RepairRequiredPayload
from tests.repair_cli.constants import GENERATION_ONE


def test_repair_verify_clears_when_only_recorded_paths_are_clean(
    repair_project: Path,
    repair_store: HookStateStore,
    clean_path_payload: RepairRequiredPayload,
) -> None:
    repair_store.mark_repair_required(GENERATION_ONE, clean_path_payload)

    result = repair.cmd_repair_verify(
        argparse.Namespace(cwd=str(repair_project), generation=GENERATION_ONE)
    )

    assert result == 0, "path-scoped verify should ignore unrelated full-repo debt"
    assert repair_store.get_repair_required() is None, (
        "clean recorded paths should clear the matching generation"
    )


def test_repair_verify_retains_when_recorded_path_is_dirty(
    repair_project: Path,
    repair_store: HookStateStore,
    targeted_debt_payload: RepairRequiredPayload,
) -> None:
    repair_store.mark_repair_required(GENERATION_ONE, targeted_debt_payload)

    result = repair.cmd_repair_verify(
        argparse.Namespace(cwd=str(repair_project), generation=GENERATION_ONE)
    )
    remaining = repair_store.get_repair_required()

    assert result != 0, "dirty recorded paths must not unlock the generation"
    assert remaining is not None, "dirty recorded paths must retain REPAIR_REQUIRED"
    assert remaining["generation"] == GENERATION_ONE, (
        "dirty recorded paths must keep the armed generation"
    )


def test_repair_verify_fails_on_known_targeted_debt(
    known_debt_project: Path,
    repair_store: HookStateStore,
    targeted_debt_payload: RepairRequiredPayload,
) -> None:
    repair_store.mark_repair_required(GENERATION_ONE, targeted_debt_payload)

    result = repair.cmd_repair_verify(
        argparse.Namespace(cwd=str(known_debt_project), generation=GENERATION_ONE)
    )
    remaining = repair_store.get_repair_required()

    assert result == 1, "known targeted debt must fail all-violation verification"
    assert remaining is not None, "known targeted debt must retain REPAIR_REQUIRED"
    assert remaining["generation"] == GENERATION_ONE, (
        "known targeted debt must keep the armed generation"
    )


def test_repair_verify_does_not_sync_baseline(
    repair_project: Path,
    repair_store: HookStateStore,
    clean_path_payload: RepairRequiredPayload,
    preserved_baseline: tuple[Path, bytes],
) -> None:
    baseline, before = preserved_baseline
    repair_store.mark_repair_required(GENERATION_ONE, clean_path_payload)

    result = repair.cmd_repair_verify(
        argparse.Namespace(cwd=str(repair_project), generation=GENERATION_ONE)
    )

    assert result == 0, "clean verification should clear the repair generation"
    assert baseline.read_bytes() == before, (
        "repair verification must not prune or rewrite the repository baseline"
    )


def test_repair_verify_retains_generation_when_recorded_path_is_missing(
    repair_project: Path,
    repair_store: HookStateStore,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = RepairRequiredPayload(
        session_id="session-one",
        call_id="call-one",
        rule_ids=["PY-CODE-015"],
        paths=["src/does-not-exist.py"],
    )
    repair_store.mark_repair_required(GENERATION_ONE, payload)

    result = repair.cmd_repair_verify(
        argparse.Namespace(cwd=str(repair_project), generation=GENERATION_ONE)
    )
    remaining = repair_store.get_repair_required()

    assert result == 1, "unresolvable recorded paths must fail closed"
    assert "do not resolve to files" in capsys.readouterr().out, (
        "missing recorded paths must explain the verification failure"
    )
    assert remaining is not None, "missing paths must retain REPAIR_REQUIRED"
    assert remaining["generation"] == GENERATION_ONE, (
        "missing paths must keep the armed generation"
    )


def test_repair_verify_rejects_recorded_project_escapes(
    rejected_escape_verification: tuple[int, str | None],
) -> None:
    result, generation = rejected_escape_verification

    assert result == 1, "recorded paths escaping the project must fail closed"
    assert generation == GENERATION_ONE, (
        "project escapes must retain the armed repair generation"
    )


@pytest.mark.usefixtures("repair_project")
def test_full_repo_lint_check_still_scans_unrelated_paths(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = cmd_lint(argparse.Namespace(lint_command="check", details=False))
    output = capsys.readouterr().out

    assert result == 1, "full-repo lint check must still fail on repo-wide violations"
    assert "oversized-module" in output, (
        "lint check must keep LINT_SCOPE_ALL and report the decoy file"
    )
