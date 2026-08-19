"""Name coverage for engine fingerprint helper."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from slopgate.lint._config import load_config, reset_config
from slopgate.lint.project_index.fingerprint import engine_fingerprint


def test_engine_fingerprint_name() -> None:
    assert engine_fingerprint.__name__ == "engine_fingerprint"


def test_engine_fingerprint_includes_all_quality_config_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_config(tmp_path)
    initial = engine_fingerprint(tmp_path)
    monkeypatch.setattr(
        "slopgate.lint._config.get_config",
        lambda: replace(config, max_line_length=80),
    )
    changed = engine_fingerprint(tmp_path)
    reset_config()

    assert changed != initial
