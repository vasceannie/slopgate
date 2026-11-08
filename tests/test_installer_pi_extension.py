from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple, cast

import pytest

import slopgate
from tests.native.commands import would_run_prefix
from tests.native.pi_support import (
    PiHarness,
    backups_preserved,
    legacy_active,
    make_harness,
    native_actions,
    native_cwds,
    package_sources,
    registered_sources,
    seed_both_scopes,
    seed_legacy,
    tree_digest,
    untouched_by_install,
    write_user_settings_text,
)


class _StagedPackage(NamedTuple):
    entry: bytes
    version: str
    name: object
    dependencies: Iterable[object]
    peer_dependencies: dict[str, object]


def _invocation_summary(harness: PiHarness) -> tuple[int, list[str], int]:
    """Summarize native install count, working directories, and call count."""
    actions = native_actions(harness.fake)
    return (
        actions.count("install"),
        native_cwds(harness.fake),
        len(harness.fake.calls()),
    )


def _install_snapshot(
    harness: PiHarness,
) -> tuple[int, dict[str, tuple[str, int]], tuple[bytes, bytes]]:
    """Capture native installs, staged files, and both settings files."""
    return (
        native_actions(harness.fake).count("install"),
        tree_digest(harness.package_root),
        (harness.user_settings.read_bytes(), harness.project_settings.read_bytes()),
    )


def _read_json(path: Path) -> dict[str, object]:
    """Read a JSON object from disk."""
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _staged_package(source: Path) -> _StagedPackage:
    """Read the staged Pi entry and manifest fields used by these contracts."""
    entry = (source / "index.ts").read_bytes()
    manifest = _read_json(source / "package.json")
    return _StagedPackage(
        entry,
        cast(str, manifest["version"]),
        manifest["name"],
        cast(Iterable[object], manifest.get("dependencies", {})),
        cast(dict[str, object], manifest["peerDependencies"]),
    )


def _refresh_observation(
    harness: PiHarness,
) -> tuple[list[str], _StagedPackage]:
    """Capture native actions and staged package contents after an install."""
    return native_actions(harness.fake), _staged_package(harness.package_root)


def _refresh_after_version_bump(
    harness: PiHarness, monkeypatch: pytest.MonkeyPatch, version: str
) -> int:
    """Bump Slopgate's version and reinstall the staged package."""
    monkeypatch.setattr(slopgate, "__version__", version)
    return harness.install(install_scope="user")


def _write_relative_package_with_empty_filter(
    harness: PiHarness,
) -> dict[str, object]:
    """Register the staged package using a relative source and empty filter."""
    relative = os.path.relpath(harness.package_root, harness.user_settings.parent)
    original: dict[str, object] = {
        "theme": "keep",
        "packages": [{"source": relative, "extensions": []}],
    }
    write_user_settings_text(harness, json.dumps(original, indent=2) + "\n")
    return original


def _user_registration_snapshot(harness: PiHarness) -> tuple[list[Path], Path]:
    """Capture user registrations and the resolved staged package source."""
    return package_sources(harness.user_settings), harness.package_root.resolve()


def test_both_scope_install_registers_same_native_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    status = harness.install()
    assert status == 0, "both-scope Pi install should complete native registration"

    user_sources, project_sources = registered_sources(harness)
    installs, cwds, invocation_count = _invocation_summary(harness)
    staged_source = harness.package_root.resolve()
    assert user_sources == [staged_source], (
        "user settings must register the staged native package source"
    )
    assert project_sources == [staged_source], (
        "project settings must register the same staged native package source"
    )
    assert installs == 2, "Pi must be invoked once per previously-unregistered scope"
    assert cwds == [str(harness.project)] * invocation_count, (
        "all Pi subprocesses must use the requested project cwd"
    )


def test_legacy_cutover_backs_up_owned_files_and_preserves_siblings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    user_seed, project_seed = seed_both_scopes(harness)
    status = harness.install()

    assert status == 0, "verified native install should retire legacy entries"
    assert not legacy_active(harness, "user"), (
        "user legacy entry points must no longer be active"
    )
    assert not legacy_active(harness, "project"), (
        "project legacy entry points must no longer be active"
    )
    assert backups_preserved(user_seed, project_seed), (
        "legacy cleanup must preserve original artifact bytes and modes in backups"
    )
    assert (harness.agent_dir / "extensions" / "pi-slopgate" / "keep.txt").exists(), (
        "unknown siblings in an owned package directory must remain untouched"
    )


def test_success_output_reports_native_source_state_and_activation_requirements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    harness = make_harness(tmp_path, monkeypatch)

    assert harness.install(install_scope="user") == 0, (
        "user-scope native package install should succeed"
    )
    output = capsys.readouterr().out
    assert "Installation mode: native package" in output, (
        "install mode must be explicit"
    )
    assert (
        str(harness.package_root) in output and "native state registered" in output
    ), "success output must show the exact source and recorded registration state"
    assert (
        "Native listing: pi list" in output
        and "Binary: /tmp/slopgate-test-bin" in output
    ), "success output must report inventory command and resolved binary"
    assert "new Pi session" in output, "success must require a fresh Pi session"


def test_reinstall_is_idempotent_and_skips_registered_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    first_status = harness.install()
    assert first_status == 0, "initial native package registration should succeed"

    installs_before, package_before, settings_before = _install_snapshot(harness)
    second_status = harness.install()
    assert second_status == 0, "reinstall of an unchanged source should succeed"

    installs_after, package_after, settings_after = _install_snapshot(harness)
    assert installs_after == installs_before, (
        "idempotent install must not rerun native package registration"
    )
    assert package_after == package_before, "staged files must remain byte-stable"
    assert settings_after == settings_before, (
        "idempotent install must preserve both native settings files"
    )


def test_version_only_upgrade_refreshes_manifest_without_changing_source_or_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    initial_status = harness.install(install_scope="user")
    assert initial_status == 0, "initial native package install should succeed"

    before = _staged_package(harness.package_root)
    next_base_version = "9.8.7-local-test"
    refresh_status = _refresh_after_version_bump(
        harness, monkeypatch, next_base_version
    )
    assert refresh_status == 0, "version-only package refresh should succeed"

    after = _staged_package(harness.package_root)
    assert after.entry == before.entry, (
        "version-only upgrade must preserve identical rendered extension bytes"
    )
    assert after.version != before.version, (
        "staged package version must change when Slopgate's base version changes"
    )
    assert after.version.startswith(next_base_version + "+local."), (
        "Pi manifest must embed the digest version derived from the new Slopgate version"
    )
    user_sources, staged_source = _user_registration_snapshot(harness)
    assert user_sources == [staged_source], (
        "Pi must preserve its stable package source during version-only refresh"
    )


def test_disabled_extension_filter_survives_explicit_package_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    original = _write_relative_package_with_empty_filter(harness)
    status = harness.install(install_scope="user")
    assert status == 0, "explicit package refresh should succeed"

    settings_after = _read_json(harness.user_settings)
    assert settings_after == original, (
        "empty extensions filter and unrelated settings must survive refresh"
    )
    output = capsys.readouterr().out
    assert "native state registered with resource filters" in output, (
        "success output must not claim an extension with an empty filter is active"
    )
    actions, staged = _refresh_observation(harness)
    assert "install" not in actions, (
        "refresh must leave the registered source/filter to the host settings"
    )
    assert staged.name == "pi-slopgate" and "@types/node" not in staged.dependencies, (
        "native package identity must avoid the legacy runtime dependency"
    )
    assert set(staged.peer_dependencies) == {
        "@earendil-works/pi-coding-agent",
        "@earendil-works/pi-tui",
    }, "Pi host peer dependencies must both be declared"


def _dry_run_names_native_commands(capsys: pytest.CaptureFixture[str]) -> bool:
    """Whether the captured dry-run output previews the install and the inventory check."""
    output = capsys.readouterr().out
    return (
        would_run_prefix("pi", "install") in output
        and "Would verify user scope with: pi list" in output
    )


def test_dry_run_does_not_change_files_or_spawn_pi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    seed_legacy(harness, "user")
    before = tree_digest(tmp_path)

    assert harness.install(dry_run=True) == 0, "read-only Pi dry-run should succeed"
    assert tree_digest(tmp_path) == before, (
        "dry-run must not create staging files or backups"
    )
    assert harness.fake.calls() == [], (
        "dry-run must not spawn Pi's mutating package commands"
    )
    assert _dry_run_names_native_commands(capsys), (
        "dry-run must print the native command and inventory target"
    )
