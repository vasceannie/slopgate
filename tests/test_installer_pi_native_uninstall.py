from __future__ import annotations

from pathlib import Path

import pytest

from tests.native.pi_support import (
    PiHarness,
    legacy_active,
    make_harness,
    package_sources,
    run_and_capture,
    seed_legacy,
)


def _hide_pi_and_seed_legacy(
    harness: PiHarness, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seed legacy files and remove the fake Pi executable from PATH."""
    seed_legacy(harness, "user")
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))


def test_missing_pi_uninstall_keeps_registered_source_but_cleans_legacy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    install_status = harness.install(install_scope="user")
    assert install_status == 0, "user setup should succeed"

    _hide_pi_and_seed_legacy(harness, tmp_path, monkeypatch)
    uninstall_status, output = run_and_capture(
        capsys, harness.uninstall, install_scope="user"
    )
    assert uninstall_status == 1, "missing native manager must be reported"
    assert "pi was not found on PATH" in output, (
        "missing manager diagnostic must be surfaced"
    )
    assert not legacy_active(harness, "user"), (
        "legacy cleanup should still run without the native CLI"
    )
    assert harness.package_root.exists() and package_sources(harness.user_settings), (
        "without Pi, keep the registered source and backing staged package"
    )
