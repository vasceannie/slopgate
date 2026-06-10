"""Suite update semantics: package update is safe unless hook refresh is explicit."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import slopgate.installer as installer_module
import slopgate.installer._suite as suite


def test_update_suite_dry_run_uses_uv_without_refreshing_hooks(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(suite, "find_binary", lambda: "slopgate")

    def uv_only(name: str) -> str | None:
        return "/usr/bin/uv" if name == "uv" else None

    monkeypatch.setattr(suite.shutil, "which", uv_only)
    (tmp_path / ".claude").mkdir()

    status = installer_module.update_suite(
        installer_module.SuiteUpdateOptions(
            dry_run=True,
            source="git+https://example.invalid/vf.git@main",
        )
    )

    output = capsys.readouterr().out
    assert (
        status,
        "Would run:" in output,
        "uv tool install --force" in output,
        "Hook refresh: skipped" in output,
        "Refreshing claude hooks" not in output,
    ) == (0, True, True, True, True)


def test_update_suite_refresh_hooks_is_explicit(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(suite, "find_binary", lambda: "slopgate")
    monkeypatch.setattr(suite.shutil, "which", lambda _name: "/usr/bin/uv")
    (tmp_path / ".claude").mkdir()

    status = installer_module.update_suite(
        installer_module.SuiteUpdateOptions(
            dry_run=True,
            source="git+https://example.invalid/vf.git@main",
            refresh_hooks=True,
        )
    )

    output = capsys.readouterr().out
    assert (
        status,
        "Would run:" in output,
        "Refreshing claude hooks" in output,
        "Would install: claude" in output,
        "Hook refresh: skipped" not in output,
    ) == (0, True, True, True, True)


def test_update_suite_dry_run_falls_back_to_pip_without_refreshing_hooks(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(suite, "find_binary", lambda: "slopgate")

    def no_binary(_name: str) -> str | None:
        return None

    monkeypatch.setattr(suite.shutil, "which", no_binary)
    (tmp_path / ".claude").mkdir()

    status = installer_module.update_suite(
        installer_module.SuiteUpdateOptions(
            dry_run=True,
            source="git+https://example.invalid/vf.git@main",
        )
    )

    output = capsys.readouterr().out
    assert (
        status,
        "Would run:" in output,
        "pip install --upgrade" in output,
        "Hook refresh: skipped" in output,
        "Refreshing claude hooks" not in output,
    ) == (0, True, True, True, True)
