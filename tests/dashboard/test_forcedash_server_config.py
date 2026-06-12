from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "dashboard" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

_config = importlib.import_module("forcedash_server.config")


def test_forcedash_default_bind_exposes_lan_and_tailnet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BIND", raising=False)

    config = importlib.reload(_config)

    assert config.BIND == "0.0.0.0", (
        "Expected ForceDash to listen on all IPv4 interfaces by default for LAN and tailnet access"
    )
