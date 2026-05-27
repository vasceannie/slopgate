from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

import vibeforcer.config as runtime_config
from vibeforcer.util import platform as platform_utils


def test_config_dir_uses_appdata_on_windows(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("VIBEFORCER_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("APPDATA", r"C:\Users\trav\AppData\Roaming")
    monkeypatch.setattr(platform_utils.sys, "platform", "win32")
    assert runtime_config.config_dir() == (
        Path(r"C:\Users\trav\AppData\Roaming") / "vibeforcer"
    )
