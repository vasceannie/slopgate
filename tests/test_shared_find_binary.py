from __future__ import annotations

import shutil
import sys

import pytest
from slopgate.installer._shared import base_invocation, find_binary


def test_find_binary_returns_slopgate_path_when_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_which(name: str) -> str | None:
        return "/usr/local/bin/slopgate" if name == "slopgate" else None

    monkeypatch.setattr(shutil, "which", _fake_which)
    result = find_binary()
    assert result == "/usr/local/bin/slopgate", f"Expected slopgate path, got {result}"


def test_find_binary_falls_back_to_sys_executable_when_not_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_which_none(name: str) -> str | None:
        return None

    monkeypatch.setattr(shutil, "which", _fake_which_none)
    result = find_binary()
    assert result == sys.executable, f"Expected sys.executable fallback, got {result}"


def test_base_invocation_returns_binary_directly_when_not_python() -> None:
    result = base_invocation("/usr/local/bin/slopgate")
    assert result == ["/usr/local/bin/slopgate"], (
        f"Expected single-element list, got {result}"
    )


def test_base_invocation_returns_module_form_when_python() -> None:
    result = base_invocation(sys.executable)
    assert result[:2] == [sys.executable, "-m"], (
        f"Expected python -m invocation, got {result}"
    )
    assert "slopgate" in result, f"Expected slopgate module in args, got {result}"
