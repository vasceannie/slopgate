"""CLI parser smoke tests."""

from __future__ import annotations

import argparse

import pytest

from slopgate.cli.cli import build_parser
from slopgate.cli.commands import cmd_test
from slopgate._types import object_dict, string_value


def _parse_lint(argv: list[str]) -> tuple[str, str | None]:
    parsed = build_parser().parse_args(argv)
    values = object_dict(vars(parsed))
    lint_command = string_value(values.get("lint_command"))
    path = string_value(values.get("path"))
    assert lint_command is not None, f"Expected lint_command in parsed args: {values}"
    return lint_command, path


def _parse_lint_details(argv: list[str]) -> bool:
    parsed = build_parser().parse_args(argv)
    values = object_dict(vars(parsed))
    return bool(values.get("details", False))


def _parse_core(argv: list[str]) -> tuple[str, str | None, bool]:
    parsed = build_parser().parse_args(argv)
    values = object_dict(vars(parsed))
    command = string_value(values.get("command"))
    path = string_value(values.get("path"))
    no_worktrees = bool(values.get("no_worktrees", False))
    assert command is not None, f"Expected command in parsed args: {values}"
    return command, path, no_worktrees


def test_lint_check_defaults_to_current_directory() -> None:
    assert _parse_lint(["lint", "check"]) == ("check", None)


def test_lint_init_respects_explicit_path() -> None:
    assert _parse_lint(["lint", "init", "/tmp/example"]) == ("init", "/tmp/example")


def test_lint_baseline_respects_explicit_path() -> None:
    assert _parse_lint(["lint", "baseline", "/tmp/example"]) == (
        "baseline",
        "/tmp/example",
    )


def test_lint_baseline_help_marks_command_disabled(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["lint", "baseline", "--help"])
    captured = capsys.readouterr()
    assert "Disabled: repo-wide rebaselining is not allowed" in captured.out


def test_lint_update_respects_explicit_path() -> None:
    assert _parse_lint(["lint", "update", "/tmp/example"]) == ("update", "/tmp/example")


def test_lint_check_rejects_explicit_path() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["lint", "check", "/tmp/example"])


def test_lint_check_details_aliases() -> None:
    assert _parse_lint_details(["lint", "check", "--details"])
    assert _parse_lint_details(["lint", "check", "--verbose"])


def test_lint_no_subcommand_defaults_to_check() -> None:
    lint_command, _path = _parse_lint(["lint"])
    assert lint_command == "check"


def test_enroll_defaults_to_current_directory() -> None:
    assert _parse_core(["enroll"]) == ("enroll", ".", False)


def test_enroll_allows_disabling_worktree_propagation() -> None:
    assert _parse_core(["enroll", "/tmp/example", "--no-worktrees"]) == (
        "enroll",
        "/tmp/example",
        True,
    )


def test_self_test_smoke_passes_all_cases(capsys: pytest.CaptureFixture[str]) -> None:
    assert cmd_test(argparse.Namespace()) == 0, "self-test smoke command should pass"
    captured = capsys.readouterr()
    assert "All tests passed." in captured.out, captured.out
    assert "git --no-verify → deny" in captured.out, captured.out
    assert "codex adapter → deny" in captured.out, captured.out
    assert "opencode adapter → deny" in captured.out, captured.out
