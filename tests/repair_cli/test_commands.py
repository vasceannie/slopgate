from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, strategies
from slopgate.cli.repair import add_repair_parsers, cmd_repair_status, cmd_repair_verify


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
def test_repair_verify_accepts_arbitrary_generation_tokens(generation: str) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        result = cmd_repair_verify(
            argparse.Namespace(cwd=tmp_dir, generation=generation)
        )

    assert result == 0, "Clean verification should not depend on generation syntax"


def test_repair_parser_registers_status_and_verify() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    add_repair_parsers(sub)

    status = parser.parse_args(["repair", "status"])
    verify = parser.parse_args(["repair", "verify", "--generation", "gen-1"])

    assert callable(status.func), "Repair status should register a CLI handler"
    assert callable(verify.func), "Repair verify should register a CLI handler"
