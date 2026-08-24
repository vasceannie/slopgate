"""Tests for the Claude skill-directory configuration migration."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from slopgate.cli.commands import cmd_config_allow_skill_directories


def _run_config_migration(
    config_path: Path,
    original: Mapping[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[int, dict[str, object], list[Path]]:
    config_path.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setenv("SLOPGATE_CONFIG", str(config_path))
    exit_code = cmd_config_allow_skill_directories(argparse.Namespace())
    updated = json.loads(config_path.read_text(encoding="utf-8"))
    backups = sorted(config_path.parent.glob("config.json.slopgate-bak-*"))
    return exit_code, updated, backups


def test_allow_skill_directories_preserves_config_and_backs_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.json"
    original = {
        "protected_paths": [
            ".claude/",
            ".claude/skills/",
            ".claude/hooks/",
            "Makefile",
        ],
        "custom": {"enabled": True},
    }
    exit_code, updated, backups = _run_config_migration(
        config_path, original, monkeypatch
    )
    assert exit_code == 0, "Configuration migration should succeed"
    assert updated == {
        "protected_paths": [".claude/hooks/", "Makefile"],
        "custom": {"enabled": True},
    }, "Only the broad Claude skill protections should be removed"
    assert len(backups) == 1, "The original config should be backed up"
    assert json.loads(backups[0].read_text(encoding="utf-8")) == original, (
        "The backup should contain the complete original config"
    )
