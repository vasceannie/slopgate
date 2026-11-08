"""Native host paths remain distinct between user and project scopes."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.constants import PLATFORM_CLAUDE
from slopgate.installer.native.paths import (
    project_host_file,
    user_host_file,
    user_host_root,
)


def test_claude_user_and_project_config_files_use_disjoint_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "operator-home"
    project = tmp_path / "repository"
    monkeypatch.setattr(Path, "home", lambda: home)

    user_root = user_host_root(PLATFORM_CLAUDE)
    user_settings = user_host_file(PLATFORM_CLAUDE, "settings.json")
    project_settings = project_host_file(PLATFORM_CLAUDE, "settings.json", project)

    assert (user_root, user_settings, project_settings) == (
        home / ".claude",
        home / ".claude" / "settings.json",
        project / ".claude" / "settings.json",
    ), (
        "Claude config helpers must root user files at HOME and project files at "
        "the selected project"
    )
    assert user_settings != project_settings, (
        "user and project settings paths must remain disjoint"
    )
