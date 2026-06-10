from __future__ import annotations
from pathlib import Path
from pytest import MonkeyPatch
import slopgate.config
from slopgate.util import platform


def test_config_dir_uses_appdata_on_windows(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("SLOPGATE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("APPDATA", "C:\\Users\\trav\\AppData\\Roaming")
    monkeypatch.setattr(platform.sys, "platform", "win32")
    assert (
        slopgate.config.config_dir()
        == Path("C:\\Users\\trav\\AppData\\Roaming") / "slopgate"
    )
