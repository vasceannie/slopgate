from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Final

import pytest
from hypothesis import given
from hypothesis import strategies

import slopgate.installer
import slopgate.installer._omp
import slopgate.installer._shared
from tests.omp_installer_support import (
    MANIFEST_BYTES,
    TEST_BINARY,
    OwnedSiteSeed,
    fail_manifest_write,
    owned_index,
    patch_install,
    patch_unreadable_artifact,
    prepare_cross_site_failure,
    site_paths,
    transaction_residue,
)

_PLACEHOLDER = '["__SLOPGATE_BIN__"]'
_BINARY_TEXT = strategies.text(
    alphabet=list("abcXYZ012/_-."), min_size=1, max_size=20
)
_TEXT_FRAGMENT = strategies.text(alphabet=list("abcXYZ012 _-."), max_size=20)
_MARKER_SUBSETS = strategies.frozensets(
    strategies.sampled_from(slopgate.installer._omp.OMP_OWNERSHIP_MARKERS)
)
_UNREADABLE_OPERATIONS: Final = (
    pytest.param(slopgate.installer._omp.install_omp, id="install"),
    pytest.param(slopgate.installer._omp.uninstall_omp, id="uninstall"),
)


@given(prefix=_TEXT_FRAGMENT, suffix=_TEXT_FRAGMENT, binary=_BINARY_TEXT)
def test_render_omp_extension_replaces_only_placeholder_property(
    prefix: str, suffix: str, binary: str
) -> None:
    rendered = slopgate.installer._omp.render_omp_extension(
        f"{prefix}{_PLACEHOLDER}{suffix}", binary
    )
    expected = (
        f"{prefix}{json.dumps(slopgate.installer._shared.base_invocation(binary))}{suffix}"
    )
    assert rendered == expected, "OMP rendering must replace only the argv placeholder"


@given(markers=_MARKER_SUBSETS)
def test_omp_index_ownership_requires_all_markers_property(
    markers: frozenset[str],
) -> None:
    content = "\n".join(sorted(markers))
    assert slopgate.installer._omp._is_owned_omp_index(content) is (
        markers == frozenset(slopgate.installer._omp.OMP_OWNERSHIP_MARKERS)
    ), "OMP index ownership must require every canonical marker"


def test_omp_agent_dir_uses_absolute_pi_coding_agent_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    configured = tmp_path / "profiles" / "active"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(configured))
    assert slopgate.installer._omp.omp_agent_dir() == configured, (
        "an absolute PI_CODING_AGENT_DIR must select the active OMP agent directory"
    )


def test_omp_agent_dir_rejects_relative_pi_coding_agent_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("PI_CODING_AGENT_DIR", "relative/agent")
    assert slopgate.installer._omp.omp_agent_dir() == home / ".omp" / "agent", (
        "a relative PI_CODING_AGENT_DIR must fall back to ~/.omp/agent"
    )


def test_omp_install_writes_exact_artifacts_and_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    patch_install(monkeypatch, home)
    assert slopgate.installer.install_platform("omp", dry_run=False) == 0, (
        "the OMP registry entry must install the user extension"
    )
    index_path, manifest_path = site_paths(home / ".omp" / "agent")
    assert index_path.read_bytes() == owned_index(TEST_BINARY), (
        "OMP install must render the packaged extension"
    )
    assert manifest_path.read_bytes() == MANIFEST_BYTES, (
        "OMP manifest bytes must use canonical insertion order and formatting"
    )
    assert not (index_path.parent / "config.json").exists(), (
        "OMP install must not create a config artifact"
    )


def test_omp_dry_run_lists_exact_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    project_root = tmp_path / "repo"
    project_root.mkdir()
    patch_install(monkeypatch, home)
    assert slopgate.installer._omp.install_omp(
        dry_run=True, scope="both", project_root=project_root
    ) == 0, "OMP dry-run should validate both sites"
    user_index, user_manifest = site_paths(home / ".omp" / "agent")
    project_index, project_manifest = site_paths(project_root / ".omp")
    assert capsys.readouterr().out.splitlines() == [
        f"Would write: {user_index}",
        f"Would write: {user_manifest}",
        f"Binary: {TEST_BINARY}",
        f"Would write: {project_index}",
        f"Would write: {project_manifest}",
        f"Binary: {TEST_BINARY}",
    ], "OMP dry-run must list only the two exact artifacts per site"


def test_omp_dry_run_does_not_create_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    project_root = tmp_path / "repo"
    project_root.mkdir()
    patch_install(monkeypatch, home)
    assert slopgate.installer._omp.install_omp(
        dry_run=True, scope="both", project_root=project_root
    ) == 0, "OMP dry-run should validate both sites"
    assert not home.exists(), "OMP dry-run must not create the absent user chain"
    assert not (project_root / ".omp").exists(), (
        "OMP dry-run must not create the project extension chain"
    )


def test_omp_install_refuses_unowned_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    patch_install(monkeypatch, home)
    index_path, manifest_path = site_paths(home / ".omp" / "agent")
    index_path.parent.mkdir(parents=True)
    custom = b"export default function custom() {}\n"
    index_path.write_bytes(custom)
    assert slopgate.installer._omp.install_omp(scope="user") == 1, (
        "OMP install must reject an unowned index"
    )
    assert index_path.read_bytes() == custom, "the unowned index must remain byte-identical"
    assert not manifest_path.exists(), "refusal must happen before creating the manifest"


def test_omp_ownership_probe_treats_unreadable_artifact_as_unowned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "index.ts"
    artifact.write_text("owned-looking content", encoding="utf-8")
    patch_unreadable_artifact(monkeypatch, artifact)
    assert not slopgate.installer._omp.omp_extension_has_owned_slopgate(artifact), (
        "an unreadable artifact cannot be established as installer-owned"
    )


@pytest.mark.parametrize("operation", _UNREADABLE_OPERATIONS)
def test_omp_lifecycle_reports_unreadable_artifact_as_nonzero_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    operation: Callable[[], int],
) -> None:
    home = tmp_path / "home"
    patch_install(monkeypatch, home)
    assert slopgate.installer._omp.install_omp() == 0, (
        "test setup must create installer-owned OMP artifacts"
    )
    index_path, _ = site_paths(home / ".omp" / "agent")
    patch_unreadable_artifact(monkeypatch, index_path)
    assert operation() == 1, "unreadable artifacts must return installer status 1"
    output = capsys.readouterr().out
    assert "Refusing to " in output and str(index_path) in output, (
        "unreadable artifacts must produce a user-facing refusal"
    )


def test_omp_same_site_failure_removes_absent_directory_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "missing-home" / "profile"
    patch_install(monkeypatch, home)
    agent_dir = home / ".omp" / "agent"
    index_path, manifest_path = site_paths(agent_dir)
    fail_manifest_write(monkeypatch, manifest_path)
    assert slopgate.installer._omp.install_omp(scope="user") == 1, (
        "same-site manifest failure must fail the install"
    )
    assert not agent_dir.exists(), "rollback must remove the transaction-created agent root"
    assert not home.exists(), "rollback must remove the transaction-created parent chain"
    assert not index_path.exists(), "rollback must remove the partial index write"


def test_omp_same_site_failure_preserves_preexisting_empty_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    patch_install(monkeypatch, home)
    agent_dir = home / ".omp" / "agent"
    index_path, manifest_path = site_paths(agent_dir)
    index_path.parent.mkdir(parents=True)
    fail_manifest_write(monkeypatch, manifest_path)
    assert slopgate.installer._omp.install_omp(scope="user") == 1, (
        "same-site manifest failure must fail the install"
    )
    expected_directories = (agent_dir, index_path.parent.parent, index_path.parent)
    assert all(directory.exists() for directory in expected_directories), (
        "rollback must preserve the full pre-existing empty directory chain"
    )
    assert not index_path.exists(), "rollback must remove only the partial artifact"


def test_omp_cross_site_failure_restores_user_bytes_and_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = prepare_cross_site_failure(monkeypatch, tmp_path)
    assert slopgate.installer._omp.install_omp(
        scope="both", project_root=scenario.project_root
    ) == 1, "project failure must roll back the completed user install"
    restored_user = OwnedSiteSeed.from_paths(
        scenario.user_index, scenario.user_manifest
    )
    assert restored_user == scenario.expected_user, (
        "cross-site rollback must restore user bytes and modes"
    )


def test_omp_cross_site_failure_restores_absent_project_topology(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = prepare_cross_site_failure(monkeypatch, tmp_path)
    assert slopgate.installer._omp.install_omp(
        scope="both", project_root=scenario.project_root
    ) == 1, "project failure must fail the multi-site install"
    assert not any(
        path.exists()
        for path in (scenario.project_root / ".omp", scenario.project_index)
    ), "cross-site rollback must restore the absent project topology"


def test_omp_cross_site_failure_leaves_no_transaction_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = prepare_cross_site_failure(monkeypatch, tmp_path)
    assert slopgate.installer._omp.install_omp(
        scope="both", project_root=scenario.project_root
    ) == 1, "project failure must fail the multi-site install"
    assert transaction_residue(tmp_path) == (), (
        "OMP rollback must leave no backup or temporary residue"
    )


def test_omp_rollback_aggregates_status_exception_and_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    completed = [tmp_path / "a", tmp_path / "b", tmp_path / "c"]
    empty = slopgate.installer._omp.ArtifactSnapshot(False, None, None)
    snapshot = slopgate.installer._omp.OmpSiteSnapshot(empty, empty, ())
    snapshots = {path: snapshot for path in completed}
    attempted: list[Path] = []

    def restore(path: Path, _snapshot: slopgate.installer._omp.OmpSiteSnapshot) -> int:
        attempted.append(path)
        if path == completed[0]:
            return 7
        if path == completed[1]:
            raise OSError("restore exploded")
        return 0

    monkeypatch.setattr(slopgate.installer._omp, "_restore_omp_site", restore)
    assert slopgate.installer._omp._rollback_omp_sites(completed, snapshots) == 1, (
        "any incomplete OMP restoration must aggregate to status 1"
    )
    assert attempted == completed, "all completed OMP sites must be attempted once in order"
    assert capsys.readouterr().err.splitlines() == [
        f"Incomplete OMP rollback: {completed[0]}: 7",
        f"Incomplete OMP rollback: {completed[1]}: restore exploded",
    ], "rollback diagnostics must report only failed restorations exactly"
