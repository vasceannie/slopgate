"""`slopgate handle` must hand Windows-resolvable paths to the daemon and engine."""

from __future__ import annotations

import argparse
import functools
import importlib
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from slopgate.cli.commands import cmd_handle
from slopgate.models import EngineResult
from tests.native.wsl_support import install_failing_wsl, install_wsl_commands

_hook_runtime = importlib.import_module("slopgate.cli.hook_runtime")
_IS_WINDOWS = "slopgate.cli.payload_paths.is_windows"
_DISTRO_ENV = "WSL_DISTRO_NAME"
_USER_ENV = "SLOPGATE_WSL_USER"
_CLAUDE = argparse.Namespace(platform="claude")
_WSL_PAYLOAD: dict[str, object] = {
    "hook_event_name": "PreToolUse",
    "cwd": "/mnt/c/Users/PC/repo",
    "tool_input": {"file_path": "/home/trav/repo/a.py"},
}
_WINDOWS_PAYLOAD: dict[str, object] = {
    "hook_event_name": "PreToolUse",
    "cwd": "C:\\Users\\PC\\repo",
    "tool_input": {"file_path": "\\\\wsl.localhost\\Ubuntu\\home\\trav\\repo\\a.py"},
}


def _feed_wsl_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_IS_WINDOWS, lambda: True)
    monkeypatch.setenv(_DISTRO_ENV, "Ubuntu")
    monkeypatch.setenv(_USER_ENV, "trav")
    install_wsl_commands(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_WSL_PAYLOAD)))


def test_cmd_handle_hands_windows_paths_to_the_daemon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handed: list[dict[str, object]] = []

    def fake_daemon(payload: dict[str, object], platform: str) -> int | None:
        handed.append(payload)
        return 0

    monkeypatch.setattr(_hook_runtime, "_try_handle_via_daemon", fake_daemon)
    _feed_wsl_payload(tmp_path, monkeypatch)

    exit_code = cmd_handle(_CLAUDE)

    assert (exit_code, handed) == (0, [_WINDOWS_PAYLOAD]), (
        "the daemon must receive drive and UNC paths so its availability cannot "
        "change enforcement"
    )


def _evaluated_without_daemon(
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, object]]:
    """Route ``handle`` to a recording in-process engine; return its payloads."""
    evaluated: list[dict[str, object]] = []

    def no_daemon(payload: dict[str, object], platform: str) -> int | None:
        return None

    def fake_evaluate(payload: dict[str, object], *, platform: str) -> EngineResult:
        evaluated.append(payload)
        return EngineResult(event_name="PreToolUse")

    monkeypatch.setattr(_hook_runtime, "_try_handle_via_daemon", no_daemon)
    monkeypatch.setattr("slopgate.engine.evaluate_payload", fake_evaluate)
    return evaluated


def test_cmd_handle_evaluates_windows_paths_without_a_daemon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evaluated = _evaluated_without_daemon(monkeypatch)
    _feed_wsl_payload(tmp_path, monkeypatch)

    exit_code = cmd_handle(_CLAUDE)

    assert (exit_code, evaluated) == (0, [_WINDOWS_PAYLOAD]), (
        "the in-process engine must evaluate drive and UNC paths, not Linux paths"
    )


_NATIVE_POSIX_PAYLOAD: dict[str, object] = {
    "hook_event_name": "PreToolUse",
    "cwd": "/c/Users/PC/repo",
    "tool_input": {"file_path": "/c/Users/PC/repo/a.py"},
}


def _feed_native_posix_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows with no forwarded distribution; any ``wsl`` call would fail."""
    monkeypatch.setattr(_IS_WINDOWS, lambda: True)
    monkeypatch.delenv(_DISTRO_ENV, raising=False)
    install_failing_wsl(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_NATIVE_POSIX_PAYLOAD)))


@pytest.mark.parametrize("platform", ("claude", "codex"))
def test_cmd_handle_evaluates_native_posix_paths_as_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    evaluated = _evaluated_without_daemon(monkeypatch)
    _feed_native_posix_payload(tmp_path, monkeypatch)

    exit_code = cmd_handle(argparse.Namespace(platform=platform))

    assert (exit_code, evaluated) == (0, [_NATIVE_POSIX_PAYLOAD]), (
        "a native Windows host (Git Bash style paths, no forwarded WSL "
        "distribution) must reach the engine unchanged, never a WSL refusal"
    )


@dataclass(frozen=True, slots=True)
class _RefusalCase:
    event: str
    exit_code: int
    decision_keys: tuple[str, ...]
    """Where the deny sits in the stdout JSON; empty when nothing is printed."""


_REFUSAL_CASES = (
    _RefusalCase("PreToolUse", 0, ("hookSpecificOutput", "permissionDecision")),
    _RefusalCase(
        "PermissionRequest", 0, ("hookSpecificOutput", "decision", "behavior")
    ),
    _RefusalCase("Stop", 1, ()),
)


def _refusal_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case: _RefusalCase,
) -> tuple[object, ...]:
    """Run ``handle`` on a WSL payload whose distribution cannot translate it."""
    evaluated: list[str] = []

    def recording_daemon(payload: dict[str, object], platform: str) -> int | None:
        evaluated.append("daemon")
        return None

    monkeypatch.setattr(_hook_runtime, "_try_handle_via_daemon", recording_daemon)
    monkeypatch.setattr(_IS_WINDOWS, lambda: True)
    monkeypatch.setenv(_DISTRO_ENV, "Ubuntu")
    monkeypatch.setenv(_USER_ENV, "trav")
    install_failing_wsl(tmp_path, monkeypatch)
    payload = {**_WSL_PAYLOAD, "hook_event_name": case.event}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    status = cmd_handle(_CLAUDE)
    captured = capsys.readouterr()
    decision = functools.reduce(
        lambda node, key: cast(dict[str, object], node)[key],
        case.decision_keys,
        cast(object, json.loads(captured.out or "null")),
    )
    return status, evaluated, decision, "Ubuntu could not translate" in captured.err


@pytest.mark.parametrize(
    "case",
    _REFUSAL_CASES,
    ids=("tool-gate-denies", "permission-denies", "lifecycle-errors"),
)
def test_cmd_handle_refuses_paths_its_distribution_cannot_translate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case: _RefusalCase,
) -> None:
    observed = _refusal_observation(tmp_path, monkeypatch, capsys, case)

    assert observed == (
        case.exit_code,
        [],
        "deny" if case.decision_keys else None,
        True,
    ), (
        "an unlocatable file must never be evaluated: tool gates get the platform "
        "deny on stdout (an exit code would not survive powershell.exe), other "
        "events report an error, and stderr names the failing distribution"
    )


_NUL_DECOY_PAYLOAD: dict[str, object] = {
    "hook_event_name": "PreToolUse",
    "cwd": "/mnt/c/Users/PC/repo\0decoy",
    "tool_input": {"file_path": "/mnt/c/Users/PC/repo/a.py"},
}


def _nul_decoy_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[object, ...]:
    """Run ``handle`` on a real edit path next to a NUL decoy path field."""
    evaluated = _evaluated_without_daemon(monkeypatch)
    _feed_wsl_payload(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_NUL_DECOY_PAYLOAD)))
    status = cmd_handle(_CLAUDE)
    output = cast(dict[str, dict[str, object]], json.loads(capsys.readouterr().out))
    return status, evaluated, output["hookSpecificOutput"]["permissionDecision"]


def test_cmd_handle_denies_a_tool_call_with_a_nul_decoy_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _nul_decoy_observation(tmp_path, monkeypatch, capsys) == (0, [], "deny"), (
        "a path no process can receive must end in the platform deny, not a "
        "crash whose exit code Claude treats as non-blocking"
    )
