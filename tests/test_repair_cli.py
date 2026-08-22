from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, strategies
from slopgate.cli import repair as repair_mod
from slopgate.cli.repair import add_repair_parsers, cmd_repair_status, cmd_repair_verify
from slopgate.state import RepairRequiredPayload

_INTENDED_LINT = [sys.executable, "-m", "slopgate", "lint", "check"]
_GENERATION_ONE = "generation-one"
_GENERATION_TWO = "generation-two"


def _mark_repair(tmp_path: Path, generation: str) -> None:
    repair_mod._store(str(tmp_path)).mark_repair_required(
        generation,
        RepairRequiredPayload(
            session_id="session-one",
            call_id="call-one",
            rule_ids=["QUALITY-LINT-001"],
            paths=["src/app.py"],
        ),
    )


def test_repair_status_command_reports_clean_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = cmd_repair_status(argparse.Namespace(cwd=str(tmp_path)))

    assert result == 0, "Repair status should succeed for an isolated worktree"
    assert json.loads(capsys.readouterr().out) == {"status": "clean"}, (
        "An unmarked worktree should report clean state"
    )


def test_repair_verify_command_is_idempotent_when_clean(tmp_path: Path) -> None:
    result = cmd_repair_verify(
        argparse.Namespace(cwd=str(tmp_path), generation="missing")
    )

    assert result == 0, "Verification should be a no-op when no repair is pending"


@given(generation=strategies.text(min_size=1, max_size=32))
def test_repair_verify_accepts_arbitrary_generation_tokens(
    generation: str,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        result = cmd_repair_verify(
            argparse.Namespace(cwd=tmp_dir, generation=generation)
        )

    assert result == 0, "Clean verification should not depend on generation syntax"


def test_repair_verify_invokes_intended_installation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mark_repair(tmp_path, _GENERATION_ONE)
    captured: list[list[str]] = []

    def _run(_cwd: Path) -> subprocess.CompletedProcess[str]:
        argv = repair_mod._lint_check_command()
        captured.append(list(argv))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(repair_mod, "_run_lint_check", _run)

    result = cmd_repair_verify(
        argparse.Namespace(cwd=str(tmp_path), generation=_GENERATION_ONE)
    )

    assert result == 0, "matching generation should verify and clear"
    assert captured == [_INTENDED_LINT], (
        "verification must invoke the intended slopgate installation"
    )
    assert repair_mod._store(str(tmp_path)).get_repair_required() is None, (
        "successful verification should clear the matching generation"
    )


def test_repair_verify_does_not_clear_replaced_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mark_repair(tmp_path, _GENERATION_ONE)
    store = repair_mod._store(str(tmp_path))

    def _run(_cwd: Path) -> subprocess.CompletedProcess[str]:
        _mark_repair(tmp_path, _GENERATION_TWO)
        return subprocess.CompletedProcess(_INTENDED_LINT, 0)

    monkeypatch.setattr(repair_mod, "_run_lint_check", _run)

    result = cmd_repair_verify(
        argparse.Namespace(cwd=str(tmp_path), generation=_GENERATION_ONE)
    )
    required = store.get_repair_required()

    assert result == 1, "a replaced generation must fail closed"
    assert required is not None, "newer repair state must survive the stale verify"
    assert required["generation"] == _GENERATION_TWO, (
        "verification must not clear a newer repair generation"
    )


def test_repair_parser_registers_status_and_verify() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    add_repair_parsers(sub)

    status = parser.parse_args(["repair", "status"])
    verify = parser.parse_args(["repair", "verify", "--generation", "gen-1"])

    assert callable(status.func), "Repair status should register a CLI handler"
    assert callable(verify.func), "Repair verify should register a CLI handler"
