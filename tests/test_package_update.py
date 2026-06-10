from __future__ import annotations

import shutil
import sys

import pytest

from slopgate.installer._suite import _package_update_command


class TestPackageUpdateCommand:
    def test_uses_uv_when_uv_on_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _fake_which(name: str) -> str | None:
            return "/usr/bin/uv" if name == "uv" else None

        monkeypatch.setattr(shutil, "which", _fake_which)
        result = _package_update_command("slopgate")
        assert result == ["/usr/bin/uv", "tool", "install", "--force", "slopgate"], (
            f"Expected uv tool install command, got {result}"
        )

    def test_uses_pip_when_uv_not_on_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fake_which_none(name: str) -> str | None:
            return None

        monkeypatch.setattr(shutil, "which", _fake_which_none)
        result = _package_update_command("slopgate")
        assert result == [sys.executable, "-m", "pip", "install", "--upgrade", "slopgate"], (
            f"Expected pip upgrade command, got {result}"
        )

    def test_uv_not_installed_uses_pip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fake_which_conditional(name: str) -> str | None:
            return None if name == "uv" else "/usr/bin/other"

        monkeypatch.setattr(shutil, "which", _fake_which_conditional)
        result = _package_update_command("slopgate")
        assert "pip" in result, (
            f"Expected pip in fallback command, got {result}"
        )
        assert "uv" not in result, (
            f"Expected no uv in fallback command, got {result}"
        )
