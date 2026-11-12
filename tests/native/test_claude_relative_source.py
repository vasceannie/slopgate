"""A marketplace Claude reports by its ./relative add source is still Slopgate's."""

from __future__ import annotations

from pathlib import Path

import pytest

import slopgate.installer
from slopgate.constants import INSTALL_SCOPE_USER
from tests.claude_installer_support import fake_calls, mutating_calls
from tests.native.claude_cutover_support import native_claude_harness


def _reinstall_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[int], list[str]]:
    """Install twice from an unrelated cwd; return statuses and marketplace mutations."""
    harness = native_claude_harness(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_CLAUDE_RELATIVE_SOURCE", "1")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    statuses = [
        slopgate.installer.install_claude(
            scope=INSTALL_SCOPE_USER, project_root=harness.project
        )
        for _ in range(2)
    ]
    calls = mutating_calls(fake_calls(harness))
    return statuses, [call[2] for call in calls if call[1] == "marketplace"]


def test_reinstall_recognizes_a_marketplace_reported_by_its_relative_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = _reinstall_observation(tmp_path, monkeypatch)

    assert observed == ([0, 0], ["add"]), (
        "a ./relative source names the staged marketplace relative to where it was "
        "added: the reinstall must accept it, never re-add or remove it"
    )
