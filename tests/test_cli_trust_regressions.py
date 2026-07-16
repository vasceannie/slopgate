"""Regression tests for CLI trust-audit bugs."""

from __future__ import annotations
import argparse
import io
import json
import shlex
import sys
from pathlib import Path
import pytest
from slopgate._types import ObjectDict, object_dict, object_list
import slopgate.installer
import slopgate.installer._shared
from slopgate.installer.hook_proxy import HOOK_PROXY_MARKER
import slopgate.search.cli
from slopgate.cli.commands import (
    cmd_check,
    cmd_config_init,
    cmd_config_path,
    cmd_config_show,
    cmd_handle,
)
from slopgate.cli.lint import cmd_lint
from slopgate.cli.main import main
from slopgate.config import resolve_git_root
from slopgate.constants import METADATA_COMMAND
from slopgate.lint._config import reset_config


def _clear_slopgate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "SLOPGATE_CONFIG",
        "SLOPGATE_CONFIG_DIR",
        "SLOPGATE_ROOT",
        "CLAUDE_HOOK_LAYER_ROOT",
        "HOOK_LAYER_ROOT",
    ):
        monkeypatch.delenv(key, raising=False)


def test_search_bare_query_dispatches_to_default_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, list[str]] = {}

    def fake_cmd_search(args: argparse.Namespace) -> int:
        observed["query"] = list(args.query)
        return 0

    monkeypatch.setattr(slopgate.search.cli, "cmd_search", fake_cmd_search)
    assert main(["search", "hello", "world"]) == 0
    assert observed == {"query": ["hello", "world"]}


def test_search_without_args_prints_help_instead_of_parse_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["search"])
    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "Semantic code search" in captured.out
    assert "query_args" not in captured.err


def _run_force_config_init(config_path: Path) -> tuple[list[Path], dict[str, object]]:
    assert cmd_config_init(argparse.Namespace(force=True)) == 0
    backups = sorted(config_path.parent.glob("config.json.slopgate-bak-*"))
    updated = json.loads(config_path.read_text(encoding="utf-8"))
    return (backups, updated)


def test_config_init_force_backs_up_existing_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_slopgate_env(monkeypatch)
    config_dir = tmp_path / "xdg" / "slopgate"
    monkeypatch.setenv("SLOPGATE_CONFIG_DIR", str(config_dir))
    config_path = config_dir / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('{"custom": true}\n', encoding="utf-8")
    backups, updated = _run_force_config_init(config_path)
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8"))["custom"] is True
    assert "custom" not in updated


def test_config_command_facade_exports_split_commands() -> None:
    assert callable(cmd_config_show)


def test_config_path_prints_resolved_config_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _clear_slopgate_env(monkeypatch)
    config_path = tmp_path / "config.json"
    config_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("SLOPGATE_CONFIG", str(config_path))
    assert cmd_config_path(argparse.Namespace()) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == str(config_path)


def test_handle_malformed_json_reports_clean_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("{not json"))
    assert cmd_handle(argparse.Namespace(platform="claude")) == 1
    captured = capsys.readouterr()
    assert "Invalid JSON on stdin" in captured.err
    assert "Traceback" not in captured.err


class _InteractiveStdin(io.StringIO):
    def isatty(self) -> bool:
        return True

    def read(self, *_args: object, **_kwargs: object) -> str:
        raise AssertionError("interactive stdin should not be read")


def test_handle_interactive_stdin_reports_clean_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", _InteractiveStdin())
    exit_code = cmd_handle(argparse.Namespace(platform="cursor"))
    captured = capsys.readouterr()
    assert {
        "exit_code": exit_code,
        "no_json": "No JSON payload on stdin" in captured.err,
        "handle_hint": "slopgate handle" in captured.err,
        "platform_hint": "--platform cursor" in captured.err,
        "no_traceback": "Traceback" not in captured.err,
    } == {
        "exit_code": 1,
        "no_json": True,
        "handle_hint": True,
        "platform_hint": True,
        "no_traceback": True,
    }


def test_check_non_git_path_is_quiet_and_does_not_create_trace_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    _clear_slopgate_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    target = tmp_path / "not-a-repo"
    target.mkdir()
    assert cmd_check(argparse.Namespace(path=str(target))) == 0
    captured = capfd.readouterr()
    assert "fatal: not a git repository" not in captured.err
    assert not (tmp_path / "xdg" / "slopgate" / "logs").exists()


def test_resolve_git_root_suppresses_git_stderr(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    assert resolve_git_root(tmp_path) is None
    captured = capfd.readouterr()
    assert "fatal: not a git repository" not in captured.err


def _dry_run_lint_update_from(path: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.chdir(path)
    reset_config()
    try:
        return cmd_lint(
            argparse.Namespace(lint_command="update", path=".", dry_run=True)
        )
    finally:
        reset_config()


def test_lint_update_discovers_project_root_from_nested_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    nested = tmp_path / "src" / "pkg"
    nested.mkdir(parents=True)
    result = _dry_run_lint_update_from(nested, monkeypatch)
    captured = capsys.readouterr()
    assert result == 0
    assert "No slopgate.toml found" not in captured.out


def _first_command(hooks: ObjectDict, event_name: str) -> str:
    entries = object_list(hooks.get(event_name))
    entry = object_dict(entries[0])
    nested = object_list(entry.get("hooks"))
    hook = object_dict(nested[0])
    command = hook[METADATA_COMMAND]
    assert isinstance(command, str)
    return command


def test_claude_installer_hook_command_quotes_binary_path_with_spaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(slopgate.installer._shared, "is_windows", lambda: False)
    binary = "/tmp/Slopgate Bin/slopgate"
    command = _first_command(
        object_dict(slopgate.installer.claude_hooks_block(binary)), "PreToolUse"
    )

    assert slopgate.installer._shared.command_is_slopgate_hook(command)
    assert HOOK_PROXY_MARKER in command
    assert shlex.join([binary, "handle"]) in command


def test_codex_installer_hook_command_quotes_binary_path_with_spaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(slopgate.installer._shared, "is_windows", lambda: False)
    binary = "/tmp/Slopgate Bin/slopgate"
    command = _first_command(
        object_dict(slopgate.installer.codex_hooks_block(binary)), "PreToolUse"
    )

    assert slopgate.installer._shared.command_is_slopgate_hook(command)
    assert HOOK_PROXY_MARKER in command
    assert shlex.join([binary, "handle", "--platform", "codex"]) in command
