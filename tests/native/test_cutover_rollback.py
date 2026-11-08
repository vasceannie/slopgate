from __future__ import annotations

import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import pytest
import slopgate.installer
import slopgate.installer.native.omp_legacy
from slopgate.constants import (
    INSTALL_SCOPE_BOTH,
    INSTALL_SCOPE_PROJECT,
    INSTALL_SCOPE_USER,
)
from slopgate.installer._omp import install_omp
from slopgate.installer.native.omp import OmpMarketplaceHost
from tests.native.omp_fake import read_fake_state
from tests.omp_installer_support import (
    TEST_BINARY,
    legacy_paths,
    prepare_omp_sandbox,
    seed_legacy,
)


class _ScopedArtifact(Protocol):
    scope: str
    path: Path


def _artifact_snapshot(
    paths: tuple[Path, ...],
) -> tuple[tuple[bytes, int], ...]:
    return tuple(
        (path.read_bytes(), stat.S_IMODE(path.stat().st_mode)) for path in paths
    )


def _inject_project_artifact_failure(
    monkeypatch: pytest.MonkeyPatch,
    user_paths: tuple[Path, ...],
    project_paths: tuple[Path, ...],
) -> list[bool]:
    remove_artifact = cast(
        Callable[[_ScopedArtifact], tuple[int, bool]],
        getattr(slopgate.installer.native.omp_legacy, "_remove_artifact"),
    )
    observed: list[bool] = []

    def fail_project(artifact: _ScopedArtifact) -> tuple[int, bool]:
        if artifact.scope == INSTALL_SCOPE_PROJECT:
            observed.append(
                all(not path.exists() for path in user_paths)
                and all(path.exists() for path in project_paths)
            )
            return 1, False
        return remove_artifact(artifact)

    monkeypatch.setattr(
        slopgate.installer.native.omp_legacy, "_remove_artifact", fail_project
    )
    return observed


@dataclass(frozen=True, slots=True)
class _ProjectFailureObservation:
    status: int
    during_failure: tuple[bool, ...]
    artifacts_restored: bool
    native_state_restored: bool
    staging_restored: bool


def _project_failure_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> _ProjectFailureObservation:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path, TEST_BINARY)
    user_paths = seed_legacy(sandbox, INSTALL_SCOPE_USER)
    project_paths = seed_legacy(sandbox, INSTALL_SCOPE_PROJECT)
    before = _artifact_snapshot(user_paths + project_paths)
    during_failure = _inject_project_artifact_failure(
        monkeypatch, user_paths, project_paths
    )
    plan = OmpMarketplaceHost().build_plan(TEST_BINARY)
    staging_before = (plan.contain_root.exists(), plan.entry_root.exists())
    status = install_omp(
        scope=INSTALL_SCOPE_BOTH,
        project_root=sandbox.project_root,
    )
    state = read_fake_state(sandbox.state_path)
    return _ProjectFailureObservation(
        status,
        tuple(during_failure),
        _artifact_snapshot(user_paths + project_paths) == before,
        (state.get("registrations"), state.get("marketplaces")) == ([], {}),
        (plan.contain_root.exists(), plan.entry_root.exists()) == staging_before,
    )


def test_project_cutover_failure_restores_removed_user_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = _project_failure_observation(tmp_path, monkeypatch)

    assert observed.status == 1, (
        "project-scope cutover failure must abort OMP installation"
    )
    assert observed.during_failure == (True,), (
        "user artifacts must be absent while project removal fails"
    )
    assert observed.artifacts_restored, (
        "OMP rollback must restore both scopes' original bytes and supported modes"
    )
    assert observed.native_state_restored, (
        "failed cross-scope installation must compensate native registrations"
    )
    assert observed.staging_restored, (
        "failed cross-scope installation must restore native staging topology"
    )


@dataclass(frozen=True, slots=True)
class _AuthoredArtifactObservation:
    status: int
    artifacts_unchanged: bool
    manager_calls: object


def _user_authored_uninstall_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> _AuthoredArtifactObservation:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path, TEST_BINARY)
    index, manifest = legacy_paths(sandbox, INSTALL_SCOPE_USER)
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_bytes(b"// user-authored OMP extension\n")
    manifest.write_bytes(b'{"extensions":["./custom.ts"]}\n')
    before = _artifact_snapshot((index, manifest))
    status = slopgate.installer.uninstall_platform(
        "omp",
        install_scope=INSTALL_SCOPE_USER,
        project_root=sandbox.project_root,
    )
    state = read_fake_state(sandbox.state_path)
    return _AuthoredArtifactObservation(
        status,
        _artifact_snapshot((index, manifest)) == before,
        state.get("calls", []),
    )


def test_uninstall_refuses_user_authored_omp_artifacts_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = _user_authored_uninstall_observation(tmp_path, monkeypatch)

    assert observed.status == 1, (
        "uninstall must refuse unrecognized user-authored OMP files"
    )
    assert observed.artifacts_unchanged, (
        "uninstall refusal must preserve both user-authored files byte-for-byte"
    )
    assert observed.manager_calls == [], (
        "legacy refusal must occur before mutating native manager commands"
    )
