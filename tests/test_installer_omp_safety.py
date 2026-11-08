from __future__ import annotations

import json
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

import slopgate.installer
import slopgate.installer._omp
import slopgate.installer._shared
from slopgate.constants import (
    INSTALL_SCOPE_BOTH,
    INSTALL_SCOPE_PROJECT,
    INSTALL_SCOPE_USER,
)
from slopgate.installer.native.marketplace.state import verification_problem
from slopgate.installer.native.model import Registration
from slopgate.installer.native.packages import native_host_root
from tests.native.omp_fake import OMP_PLUGIN_ID, read_fake_state
from tests.omp_installer_support import (
    REFRESHED_BINARY,
    OmpSandbox,
    entries_for_scope,
    native_inventory,
    prepare_omp_sandbox,
    seed_legacy,
    set_fake_failure,
    tree_hash,
)


def _legacy_snapshot(paths: tuple[Path, ...]) -> tuple[tuple[bytes, int], ...]:
    return tuple(
        (path.read_bytes(), stat.S_IMODE(path.stat().st_mode)) for path in paths
    )


def _staged_version() -> str:
    stage_root = native_host_root("omp") / "marketplace"
    catalog = cast(
        dict[str, object],
        json.loads((stage_root / ".omp-plugin" / "marketplace.json").read_text()),
    )
    plugin = cast(dict[str, object], cast(list[object], catalog["plugins"])[0])
    return str(plugin["version"])


def _seed_prior_disabled_install(
    sandbox: OmpSandbox,
) -> tuple[
    dict[str, object], tuple[Path, ...], tuple[tuple[bytes, int], ...], Path, str
]:
    assert slopgate.installer._omp.install_omp() == 0, (
        "test setup should create a prior native user registration"
    )
    subprocess.run(
        [
            str(sandbox.launcher),
            "plugin",
            "disable",
            "--scope",
            INSTALL_SCOPE_USER,
            OMP_PLUGIN_ID,
        ],
        cwd=sandbox.project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    inventory = native_inventory(sandbox, sandbox.project_root)
    prior = entries_for_scope(inventory, INSTALL_SCOPE_USER)[0]
    legacy = seed_legacy(sandbox, INSTALL_SCOPE_USER) + seed_legacy(
        sandbox, INSTALL_SCOPE_PROJECT
    )
    stage_root = native_host_root("omp")
    return prior, legacy, _legacy_snapshot(legacy), stage_root, tree_hash(stage_root)


@dataclass(frozen=True, slots=True)
class _DryRunOutcome:
    status: int
    output: str
    before: str
    staging: Path
    legacy: tuple[Path, ...]


def _run_dry_run(
    sandbox: OmpSandbox,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> _DryRunOutcome:
    legacy = seed_legacy(sandbox, INSTALL_SCOPE_USER)
    before = tree_hash(tmp_path)
    staging = native_host_root("omp")
    status = slopgate.installer._omp.install_omp(
        dry_run=True, scope=INSTALL_SCOPE_BOTH, project_root=sandbox.project_root
    )
    output = capsys.readouterr().out
    return _DryRunOutcome(status, output, before, staging, legacy)


@dataclass(frozen=True, slots=True)
class _MissingCliOutcome:
    install_status: int
    legacy_before: tuple[tuple[bytes, int], ...]
    legacy: tuple[Path, ...]


def _exercise_missing_cli(
    sandbox: OmpSandbox, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> _MissingCliOutcome:
    legacy = seed_legacy(sandbox, INSTALL_SCOPE_USER)
    before = _legacy_snapshot(legacy)
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))
    install_status = slopgate.installer._omp.install_omp()
    return _MissingCliOutcome(install_status, before, legacy)


@dataclass(frozen=True, slots=True)
class _PartialFailureOutcome:
    status: int
    user_after: list[dict[str, object]]
    project_after: list[dict[str, object]]


def _run_partial_failure(
    sandbox: OmpSandbox, monkeypatch: pytest.MonkeyPatch
) -> _PartialFailureOutcome:
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: REFRESHED_BINARY
    )
    set_fake_failure(monkeypatch, "plugin install --scope project", after_mutation=True)
    status = slopgate.installer._omp.install_omp(
        scope=INSTALL_SCOPE_BOTH, project_root=sandbox.project_root
    )
    inventory = native_inventory(sandbox, sandbox.project_root)
    return _PartialFailureOutcome(
        status,
        entries_for_scope(inventory, INSTALL_SCOPE_USER),
        entries_for_scope(inventory, INSTALL_SCOPE_PROJECT),
    )


def _capture_rollback_state(
    legacy: tuple[Path, ...], stage_root: Path
) -> tuple[tuple[tuple[bytes, int], ...], str, str]:
    return _legacy_snapshot(legacy), tree_hash(stage_root), _staged_version()


@dataclass(frozen=True, slots=True)
class _SymlinkEscapeOutcome:
    status: int
    external_paths: tuple[Path, Path]
    external_before: tuple[tuple[bytes, int], ...]


def _run_project_symlink_escape(
    sandbox: OmpSandbox, tmp_path: Path
) -> _SymlinkEscapeOutcome:
    external_root = tmp_path / "external"
    external_index = external_root / "extensions" / "omp-slopgate" / "index.ts"
    external_manifest = external_index.with_name("package.json")
    external_index.parent.mkdir(parents=True)
    external_index.write_text("foreign extension", encoding="utf-8")
    external_manifest.write_text("foreign manifest", encoding="utf-8")
    (sandbox.project_root / ".omp").symlink_to(external_root)
    external_paths = (external_index, external_manifest)
    external_before = _legacy_snapshot(external_paths)
    status = slopgate.installer._omp.install_omp(
        scope=INSTALL_SCOPE_PROJECT, project_root=sandbox.project_root
    )
    return _SymlinkEscapeOutcome(status, external_paths, external_before)


def test_omp_dry_run_is_read_only_and_reports_project_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path)
    outcome = _run_dry_run(sandbox, tmp_path, capsys)
    assert outcome.status == 0, "dry-run should complete read-only migration preflight"
    assert str(sandbox.project_root / ".omp") in outcome.output, (
        "dry-run should report the missing OMP project anchor"
    )
    assert tree_hash(tmp_path) == outcome.before, (
        "OMP dry-run should leave every sandbox file and directory unchanged"
    )
    assert not (sandbox.project_root / ".omp").exists(), (
        "dry-run should report but not create the OMP project anchor"
    )
    assert not outcome.staging.exists(), (
        "dry-run should not create native staging or catalog files"
    )
    assert all(path.exists() for path in outcome.legacy), (
        "dry-run should leave supported legacy enforcement artifacts in place"
    )
    assert not sandbox.state_path.exists(), (
        "read-only native inventory commands should not write fake manager state"
    )


def test_missing_omp_cli_keeps_legacy_install_and_allows_legacy_only_uninstall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path)
    outcome = _exercise_missing_cli(sandbox, tmp_path, monkeypatch)
    assert outcome.install_status == 1, (
        "missing native OMP CLI should fail installation"
    )
    assert _legacy_snapshot(outcome.legacy) == outcome.legacy_before, (
        "missing CLI should leave the active legacy extension bytes and modes unchanged"
    )
    assert read_fake_state(sandbox.state_path)["calls"] == [], (
        "missing CLI should be detected before invoking a native manager command"
    )
    uninstall_status = slopgate.installer.uninstall_platform("omp")
    assert uninstall_status == 0, (
        "legacy-only uninstall should work without the OMP CLI"
    )
    assert all(not path.exists() for path in outcome.legacy), (
        "legacy-only uninstall should remove only the recognized selected-scope files"
    )


def test_both_scope_partial_failure_restores_prior_registration_and_legacy_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path)
    prior, legacy, legacy_before, stage_root, staging_before = (
        _seed_prior_disabled_install(sandbox)
    )
    outcome = _run_partial_failure(sandbox, monkeypatch)
    legacy_after, staging_after, staged_version = _capture_rollback_state(
        legacy, stage_root
    )
    assert (
        outcome.status == 1,
        len(outcome.user_after) == 1
        and outcome.user_after[0].get("version") == prior.get("version")
        and outcome.user_after[0].get("enabled") is False,
        outcome.project_after == [],
        legacy_after == legacy_before,
        staging_after == staging_before,
        staged_version == str(prior["version"]),
    ) == (True, True, True, True, True, True), (
        "failed project registration must restore the disabled user version, "
        "remove project registration, and preserve legacy artifacts and staging"
    )


def test_malformed_legacy_manifest_refuses_before_native_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path)
    _, manifest = seed_legacy(sandbox, INSTALL_SCOPE_USER)
    manifest.write_text("{ malformed json", encoding="utf-8")
    malformed_bytes = manifest.read_bytes()
    status = slopgate.installer._omp.install_omp()
    assert status == 1, "malformed legacy OMP manifest should be refused"
    assert manifest.read_bytes() == malformed_bytes, (
        "malformed legacy metadata should remain byte-identical after refusal"
    )
    assert read_fake_state(sandbox.state_path)["calls"] == [], (
        "legacy preflight should refuse malformed metadata before native mutations"
    )


def test_project_symlink_escape_is_refused_without_touching_external_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path)
    outcome = _run_project_symlink_escape(sandbox, tmp_path)
    assert outcome.status == 1, (
        "project-scope OMP migration should refuse an escaping symlink"
    )
    assert _legacy_snapshot(outcome.external_paths) == outcome.external_before, (
        "containment refusal should preserve files outside the requested project root"
    )
    assert read_fake_state(sandbox.state_path)["calls"] == [], (
        "path containment should be checked before any native manager command"
    )


def test_project_install_refuses_unsafe_local_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path)
    unsafe_anchor = sandbox.project_root / ".omp"
    unsafe_anchor.write_text("not a directory", encoding="utf-8")

    status = slopgate.installer._omp.install_omp(
        scope=INSTALL_SCOPE_PROJECT, project_root=sandbox.project_root
    )

    assert status == 1, "a non-directory local OMP anchor must be refused"
    assert unsafe_anchor.read_text(encoding="utf-8") == "not a directory", (
        "unsafe local anchor content must remain untouched"
    )


def test_project_install_refuses_native_ancestor_anchor_without_creating_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path)
    (tmp_path / ".git").mkdir()
    status = slopgate.installer._omp.install_omp(
        scope=INSTALL_SCOPE_PROJECT, project_root=sandbox.project_root
    )
    assert status == 1, "OMP should refuse a project scope resolved to a Git ancestor"
    assert not (sandbox.project_root / ".omp").exists(), (
        "ancestor-anchor refusal should not create a project-local OMP anchor"
    )
    assert read_fake_state(sandbox.state_path)["calls"] == [], (
        "project anchoring should be validated before marketplace manager mutations"
    )


def test_omp_verification_rejects_a_previously_enabled_plugin_becoming_disabled() -> (
    None
):
    prior = Registration(OMP_PLUGIN_ID, INSTALL_SCOPE_USER, "prior", True, None)
    current = Registration(OMP_PLUGIN_ID, INSTALL_SCOPE_USER, "current", False, None)
    problem = verification_problem(current, prior, "current")
    assert problem == "native enabled state False does not match previous state True", (
        "native verification must reject any change from the recorded enabled state"
    )
