"""Suite update semantics: package update is safe unless hook refresh is explicit."""

from __future__ import annotations
import pytest
from pathlib import Path
import slopgate.installer
import slopgate.installer._suite


def test_update_suite_dry_run_uses_uv_without_refreshing_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(slopgate.installer._suite, "find_binary", lambda: "slopgate")

    def uv_only(name: str) -> str | None:
        return "/usr/bin/uv" if name == "uv" else None

    monkeypatch.setattr(slopgate.installer._suite.shutil, "which", uv_only)
    (tmp_path / ".claude").mkdir()
    status = slopgate.installer.update_suite(
        slopgate.installer.SuiteUpdateOptions(
            dry_run=True, source="git+https://example.invalid/vf.git@main"
        )
    )
    output = capsys.readouterr().out
    assert (
        status,
        "Would run:" in output,
        "tool" in output and "install" in output and "--force" in output,
        "Hook refresh: skipped" in output,
        "Refreshing claude hooks" not in output,
    ) == (0, True, True, True, True)


def test_update_suite_refresh_hooks_is_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(slopgate.installer._suite, "find_binary", lambda: "slopgate")

    def fake_which(_name: str) -> str:
        return "/usr/bin/uv"

    monkeypatch.setattr(slopgate.installer._suite.shutil, "which", fake_which)
    (tmp_path / ".claude").mkdir()
    status = slopgate.installer.update_suite(
        slopgate.installer.SuiteUpdateOptions(
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(slopgate.installer._suite, "find_binary", lambda: "slopgate")

    def no_binary(_name: str) -> str | None:
        return None

    monkeypatch.setattr(slopgate.installer._suite.shutil, "which", no_binary)
    (tmp_path / ".claude").mkdir()
    status = slopgate.installer.update_suite(
        slopgate.installer.SuiteUpdateOptions(
            dry_run=True, source="git+https://example.invalid/vf.git@main"
        )
    )
    output = capsys.readouterr().out
    assert (
        status,
        "Would run:" in output,
        "pip" in output and "install" in output and "--upgrade" in output,
        "Hook refresh: skipped" in output,
        "Refreshing claude hooks" not in output,
    ) == (0, True, True, True, True)
