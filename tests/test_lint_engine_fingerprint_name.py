"""Name coverage for engine fingerprint helper."""

from __future__ import annotations

from slopgate.lint.project_index.fingerprint import engine_fingerprint


def test_engine_fingerprint_name() -> None:
    assert engine_fingerprint.__name__ == "engine_fingerprint"
