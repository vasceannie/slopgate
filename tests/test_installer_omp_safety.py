from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest
from hypothesis import given, strategies

import slopgate.installer._omp
import slopgate.installer._shared
from slopgate.installer import install_omp, uninstall_omp
from tests.omp_installer_support import patch_install, site_paths


@given(segment=strategies.from_regex(r"[A-Za-z0-9_-]{1,16}", fullmatch=True))
def test_omp_agent_dir_rejects_arbitrary_relative_overrides(segment: str) -> None:
    home = Path("/tmp/omp-resolver-home")
    with patch.dict(
        os.environ,
        {"HOME": str(home), "PI_CODING_AGENT_DIR": f"{segment}/agent"},
    ):
        assert slopgate.installer._omp.omp_agent_dir() == home / ".omp" / "agent", (
            "relative PI_CODING_AGENT_DIR values must not escape the home fallback"
        )


@given(depth=strategies.integers(min_value=1, max_value=5))
def test_omp_rollback_removes_arbitrary_missing_parent_chains(depth: int) -> None:
    with TemporaryDirectory() as temporary_directory:
        anchor = Path(temporary_directory)
        home = anchor.joinpath(*(f"missing-{level}" for level in range(depth)))
        original_write = slopgate.installer._omp.write_contained_text
        writes = 0

        def fail_manifest_write(
            path: Path,
            content: str,
            write: slopgate.installer._shared.ContainedWrite,
        ) -> Path:
            nonlocal writes
            writes += 1
            if writes == 2:
                raise OSError("simulated manifest write failure")
            return original_write(path, content, write)

        with (
            patch.dict(
                os.environ,
                {"OMP_AGENT_DIR": "", "PI_CODING_AGENT_DIR": ""},
            ),
            patch.object(Path, "home", return_value=home),
            patch.object(
                slopgate.installer._omp,
                "write_contained_text",
                side_effect=fail_manifest_write,
            ),
        ):
            status = install_omp(dry_run=False)

        assert status == 1, "the injected manifest failure should fail installation"
        assert not home.exists(), (
            "rollback should remove every parent created below the nearest existing anchor"
        )


def test_omp_install_preserves_an_unowned_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    patch_install(monkeypatch, home)
    index_path, manifest_path = site_paths(home / ".omp" / "agent")
    manifest_path.parent.mkdir(parents=True)
    unowned_manifest = '{"name":"unowned-extension"}\n'
    manifest_path.write_text(unowned_manifest, encoding="utf-8")

    assert install_omp(dry_run=False) == 1, (
        "install should refuse a site containing an unowned manifest"
    )
    assert not index_path.exists(), "refused install should not create an index artifact"
    assert manifest_path.read_text(encoding="utf-8") == unowned_manifest, (
        "refused install should preserve the unowned manifest byte-for-byte"
    )


@pytest.mark.parametrize(
    "unowned_artifact",
    [
        pytest.param("index", id="unowned-index"),
        pytest.param("manifest", id="unowned-manifest"),
    ],
)
def test_omp_uninstall_preserves_each_unowned_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unowned_artifact: str,
) -> None:
    home = tmp_path / "home"
    patch_install(monkeypatch, home)
    index_path, manifest_path = site_paths(home / ".omp" / "agent")
    expected_path = index_path if unowned_artifact == "index" else manifest_path
    assert install_omp(dry_run=False) == 0, "test setup should install owned artifacts"
    expected_path.write_text(f"unowned {unowned_artifact}", encoding="utf-8")
    expected_text = expected_path.read_text(encoding="utf-8")

    assert uninstall_omp() == 1, "uninstall should report an unowned artifact as refused"
    assert expected_path.read_text(encoding="utf-8") == expected_text, (
        "uninstall should preserve each unowned artifact byte-for-byte"
    )
