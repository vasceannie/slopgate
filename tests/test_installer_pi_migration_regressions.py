from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

import slopgate.installer
import slopgate.installer._suite
import slopgate.installer.native.entry
from slopgate.constants import (
    INSTALL_SCOPE_BOTH,
    INSTALL_SCOPE_PROJECT,
    INSTALL_SCOPE_USER,
)
from slopgate.installer._suite import InstallSite, SuiteUpdateOptions
from tests.native.pi_support import (
    PiHarness,
    backups_preserved,
    legacy_paths,
    make_harness,
    native_mutations,
    registered_sources,
    seed_legacy,
    seed_unrecognized_legacy_directory,
    tree_digest,
)

_UNRECOGNIZED_LEGACY_FILES = [
    pytest.param(
        (("index.ts", "// foreign Pi extension\n"),), id="foreign-active-entry"
    ),
    pytest.param(
        (
            ("package.json", '{"peerDependencies":{"@earendil-works/pi-tui":"*"}}'),
            ("config.json", '{"name":"pi-slopgate"}'),
        ),
        id="metadata-only-without-entry",
    ),
]
_KEEP_SIBLING_CONTENT = (b"user keep\n", b"project keep\n")


def _seed_keep_siblings(harness: PiHarness) -> tuple[Path, Path]:
    user_keep = legacy_paths(harness, INSTALL_SCOPE_USER)[0].parent / "keep.txt"
    project_keep = legacy_paths(harness, INSTALL_SCOPE_PROJECT)[0].parent / "keep.txt"
    user_keep.write_bytes(_KEEP_SIBLING_CONTENT[0])
    project_keep.write_bytes(_KEEP_SIBLING_CONTENT[1])
    return user_keep, project_keep


def _keep_siblings_match(paths: tuple[Path, Path]) -> bool:
    return tuple(path.read_bytes() for path in paths) == _KEEP_SIBLING_CONTENT


def _no_op_package_update(_source: str) -> list[str]:
    return [sys.executable, "-c", "pass"]


def _refresh_pi_from_suite(harness: PiHarness, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(
        slopgate.installer._suite,
        "_package_update_command",
        _no_op_package_update,
    )

    def discover_pi_site(include_missing: bool = False) -> list[InstallSite]:
        _ = include_missing
        return [InstallSite("pi", harness.project, True)]

    monkeypatch.setattr(
        slopgate.installer._suite, "discover_install_sites", discover_pi_site
    )
    monkeypatch.setattr(
        slopgate.installer.native.entry, "find_binary", lambda: "slopgate-refreshed"
    )
    return slopgate.installer.update_suite(
        SuiteUpdateOptions(
            refresh_hooks=True,
            install_scope=INSTALL_SCOPE_BOTH,
            project_root=harness.project,
        )
    )


def _seed_migration_scopes(
    harness: PiHarness,
) -> tuple[dict[Path, tuple[bytes, int]], dict[Path, tuple[bytes, int]]]:
    """Seed recognized legacy files and preserve unrelated package siblings."""
    return (
        seed_legacy(harness, INSTALL_SCOPE_USER),
        seed_legacy(harness, INSTALL_SCOPE_PROJECT),
    )


def _refusal_observations(
    harness: PiHarness, legacy_directory: Path
) -> tuple[bool, bool, bool]:
    """Capture native-call, staging, and legacy-directory state after refusal."""
    return (
        harness.fake.calls() == [],
        not harness.package_root.exists(),
        legacy_directory.is_dir(),
    )


@dataclass(frozen=True, slots=True)
class _MigrationLifecycleObservation:
    initial_status: int
    initial_mutations: tuple[str, ...]
    initial_backups_preserved: bool
    initial_siblings_preserved: bool
    reinstall_status: int
    reinstall_mutations_preserved: bool
    reinstall_siblings_preserved: bool
    refresh_status: int
    refresh_registrations_preserved: bool
    refresh_mutations_preserved: bool
    refresh_siblings_preserved: bool
    uninstall_status: int
    uninstalled_sources_empty: bool
    uninstall_backups_preserved: bool
    uninstall_siblings_preserved: bool


def _migration_lifecycle_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> _MigrationLifecycleObservation:
    harness = make_harness(tmp_path, monkeypatch)
    user_seed, project_seed = _seed_migration_scopes(harness)
    keep_paths = _seed_keep_siblings(harness)
    initial_status = harness.install(install_scope=INSTALL_SCOPE_BOTH)
    initial_mutations = tuple(native_mutations(harness.fake))
    initial_backups = backups_preserved(user_seed, project_seed)
    initial_siblings = _keep_siblings_match(keep_paths)
    reinstall_status = harness.install(install_scope=INSTALL_SCOPE_BOTH)
    reinstall_mutations = tuple(native_mutations(harness.fake)) == initial_mutations
    reinstall_siblings = _keep_siblings_match(keep_paths)
    prior_sources = registered_sources(harness)
    refresh_status = _refresh_pi_from_suite(harness, monkeypatch)
    refresh_registrations = registered_sources(harness) == prior_sources
    refresh_mutations = tuple(native_mutations(harness.fake)) == initial_mutations
    refresh_siblings = _keep_siblings_match(keep_paths)
    uninstall_status = harness.uninstall(install_scope=INSTALL_SCOPE_BOTH)
    return _MigrationLifecycleObservation(
        initial_status,
        initial_mutations,
        initial_backups,
        initial_siblings,
        reinstall_status,
        reinstall_mutations,
        reinstall_siblings,
        refresh_status,
        refresh_registrations,
        refresh_mutations,
        refresh_siblings,
        uninstall_status,
        registered_sources(harness) == ([], []),
        backups_preserved(user_seed, project_seed),
        _keep_siblings_match(keep_paths),
    )


def _migration_lifecycle_matches(observed: _MigrationLifecycleObservation) -> bool:
    return (
        observed.initial_status,
        observed.initial_mutations,
        observed.initial_backups_preserved,
        observed.initial_siblings_preserved,
        observed.reinstall_status,
        observed.reinstall_mutations_preserved,
        observed.reinstall_siblings_preserved,
        observed.refresh_status,
        observed.refresh_registrations_preserved,
        observed.refresh_mutations_preserved,
        observed.refresh_siblings_preserved,
        observed.uninstall_status,
        observed.uninstalled_sources_empty,
        observed.uninstall_backups_preserved,
        observed.uninstall_siblings_preserved,
    ) == (
        0,
        ("install", "install"),
        True,
        True,
        0,
        True,
        True,
        0,
        True,
        True,
        True,
        0,
        True,
        True,
        True,
    )


def test_reinstall_refresh_and_uninstall_preserve_unrelated_pi_siblings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = _migration_lifecycle_observation(tmp_path, monkeypatch)

    assert _migration_lifecycle_matches(observed), (
        "install, reinstall, suite refresh, and uninstall must preserve backups, sibling bytes, and native registrations"
    )


def test_unrelated_only_pi_extension_directory_is_safe_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    legacy_directory = seed_unrecognized_legacy_directory(
        harness, (("notes.txt", "keep this note\n"),)
    )
    note = legacy_directory / "notes.txt"
    before = note.read_bytes()

    status = harness.install(install_scope=INSTALL_SCOPE_USER)

    assert status == 0, "an unrelated-only old extension directory must be a safe no-op"
    assert note.read_bytes() == before, (
        "cutover must leave the unrelated-only directory byte-identical"
    )


@pytest.mark.parametrize("legacy_files", _UNRECOGNIZED_LEGACY_FILES)
def test_unrecognized_pi_legacy_directory_refuses_before_native_mutation(
    legacy_files: tuple[tuple[str, str], ...],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    legacy_directory = seed_unrecognized_legacy_directory(harness, legacy_files)
    before = tree_digest(tmp_path)

    status = harness.install(install_scope=INSTALL_SCOPE_USER)
    assert status == 1, "metadata-only and foreign active entries must be refused"
    assert tree_digest(tmp_path) == before, (
        "unsafe legacy preflight must preserve the complete sandbox tree"
    )
    no_native_calls, no_staging, legacy_directory_present = _refusal_observations(
        harness, legacy_directory
    )
    assert no_native_calls, "refusal must happen before any native Pi command"
    assert no_staging, "refusal must happen before package staging"
    assert legacy_directory_present, "refused legacy inputs must remain in place"
