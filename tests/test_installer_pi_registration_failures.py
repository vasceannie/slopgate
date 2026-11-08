from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

import pytest

from slopgate.installer.native.packages import PackagePlan, StagingSnapshot
from slopgate.installer.native.pi import install as pi_install
from tests.native.pi_support import (
    PiHarness,
    artifacts_unchanged,
    make_harness,
    no_approval_flags,
    original_artifacts_match,
    package_sources,
    registered_sources,
    run_and_capture,
    seed_legacy,
    seed_both_scopes,
    untouched_by_install,
    write_user_settings_text,
)


def _seed_metadata_only_package(harness: PiHarness) -> tuple[Path, Path]:
    """Create an owned-looking Pi package directory without an entry point."""
    package = harness.agent_dir / "extensions" / "pi-slopgate"
    package.mkdir(parents=True)
    (package / "package.json").write_text(
        json.dumps({"peerDependencies": {"@earendil-works/pi-tui": "*"}}),
        encoding="utf-8",
    )
    config = package / "config.json"
    config.write_text(json.dumps({"name": "pi-slopgate"}), encoding="utf-8")
    return package, config


def _seed_untrusted_project(harness: PiHarness) -> dict[Path, tuple[bytes, int]]:
    """Seed project legacy files and mark the project untrusted."""
    seeded = seed_legacy(harness, "project")
    harness.fake.set_project_trusted(False)
    return seeded


def _project_registration_snapshot(harness: PiHarness) -> tuple[list[Path], Path]:
    """Capture project registrations and the resolved staged package source."""
    return package_sources(harness.project_settings), harness.package_root.resolve()


class _SelectedScopeSnapshot(NamedTuple):
    install_status: int
    uninstall_status: int
    project_settings_before: bytes
    project_settings_after: bytes
    user_sources: list[Path]
    project_sources: list[Path]
    staged_source: Path
    staging_present: bool


def _selected_scope_uninstall_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> _SelectedScopeSnapshot:
    harness = make_harness(tmp_path, monkeypatch)
    install_status = harness.install()
    project_settings_before = harness.project_settings.read_bytes()
    uninstall_status = harness.uninstall(install_scope="user")
    user_sources, project_sources = registered_sources(harness)
    return _SelectedScopeSnapshot(
        install_status,
        uninstall_status,
        project_settings_before,
        harness.project_settings.read_bytes(),
        user_sources,
        project_sources,
        harness.package_root.resolve(),
        harness.package_root.exists(),
    )


def test_missing_pi_cli_fails_before_legacy_or_staging_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    seeded = seed_legacy(harness, "user")
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))

    assert harness.install(install_scope="user") == 1, (
        "missing Pi CLI must return nonzero"
    )
    assert original_artifacts_match(seeded), (
        "missing Pi CLI must leave legacy bytes and modes intact"
    )
    assert not harness.package_root.exists(), (
        "missing Pi CLI must not create package staging"
    )


def test_partial_project_registration_failure_rolls_back_all_created_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    user_seed, project_seed = seed_both_scopes(harness)
    harness.fake.fail("install", "project", mutate_before_failure=True)

    status = harness.install()

    assert status == 1, "partially mutating project install must abort transaction"
    user_sources, project_sources = registered_sources(harness)
    assert user_sources == [] and project_sources == [], (
        "rollback must remove registrations created in user and project scope"
    )
    assert artifacts_unchanged(user_seed, project_seed), (
        "rollback must restore original legacy artifact bytes and modes"
    )
    assert not harness.package_root.exists(), (
        "rollback must restore absent staging state"
    )


def test_malformed_settings_refuse_before_any_install_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    write_user_settings_text(harness, "{bad json")
    seeded = seed_legacy(harness, "user")

    status = harness.install(install_scope="user")

    assert status == 1, "malformed Pi settings must refuse preflight"
    assert harness.user_settings.read_text(encoding="utf-8") == "{bad json", (
        "malformed settings must remain byte-identical"
    )
    assert original_artifacts_match(seeded), (
        "malformed settings refusal must preserve legacy files"
    )
    assert untouched_by_install(harness), (
        "malformed settings must be detected before staging or native commands"
    )


def test_legacy_metadata_without_owned_entry_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    package, config = _seed_metadata_only_package(harness)

    status = harness.install(install_scope="user")

    assert status == 1, "metadata alone must not claim an arbitrary Pi package"
    assert config.exists() and (package / "package.json").exists(), (
        "refused legacy metadata must remain untouched"
    )
    assert not harness.package_root.exists(), (
        "ownership refusal must happen before staging"
    )


def test_selected_scope_uninstall_preserves_other_scope_and_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _selected_scope_uninstall_snapshot(tmp_path, monkeypatch)

    assert (snapshot.install_status, snapshot.uninstall_status) == (0, 0), (
        "both-scope setup and selected user uninstall should succeed"
    )
    assert snapshot.user_sources == [], "user package source should be removed"
    assert snapshot.project_sources == [snapshot.staged_source], (
        "project package registration must remain intact"
    )
    assert snapshot.project_settings_after == snapshot.project_settings_before, (
        "selected user uninstall must preserve project settings bytes"
    )
    assert snapshot.staging_present, "shared staged package must remain for other scope"


def test_untrusted_project_remove_is_reported_without_approval_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    install_status = harness.install()
    assert install_status == 0, "both-scope setup should succeed"

    legacy = _seed_untrusted_project(harness)
    remove_status, output = run_and_capture(
        capsys, harness.uninstall, install_scope="project"
    )
    assert remove_status == 1, "Pi trust refusal must return failure"
    assert "Project is not trusted. Use --approve" in output, (
        "native trust diagnostic must be surfaced"
    )
    project_sources, staged_source = _project_registration_snapshot(harness)
    assert project_sources == [staged_source], (
        "failed native remove must preserve project settings"
    )
    assert original_artifacts_match(legacy), (
        "failed native remove must not retire legacy files"
    )
    assert no_approval_flags(harness.fake), "Slopgate must not bypass project trust"


def _swap_staging_to_symlink_before_snapshot(
    monkeypatch: pytest.MonkeyPatch, outside: Path
) -> None:
    """Replace the planned package root with a symlink once preflight has passed."""
    outside.mkdir()
    real_snapshot = pi_install.snapshot_staging

    def swap_then_snapshot(plan: PackagePlan) -> StagingSnapshot:
        plan.entry_root.parent.mkdir(parents=True, exist_ok=True)
        plan.entry_root.symlink_to(outside, target_is_directory=True)
        return real_snapshot(plan)

    monkeypatch.setattr(pi_install, "snapshot_staging", swap_then_snapshot)


def test_staging_symlink_swap_after_preflight_fails_cleanly_without_escaping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    seeded = seed_legacy(harness, "user")
    _swap_staging_to_symlink_before_snapshot(monkeypatch, tmp_path / "outside")

    status = harness.install(install_scope="user")

    assert status == 1, "a staging path swapped to a symlink must fail with status 1"
    assert not list((tmp_path / "outside").iterdir()), "nothing written via symlink"
    assert original_artifacts_match(seeded), "legacy enforcement must stay intact"
    assert "Refusing" in capsys.readouterr().out, "the refusal must be reported"
