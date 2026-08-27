from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies

import slopgate.installer
import slopgate.installer._omp
import slopgate.installer._shared
from tests.omp_installer_support import (
    MANIFEST_PAYLOAD,
    TEST_BINARY,
    OwnedSiteSeed,
    fail_manifest_write,
    owned_index,
    patch_install,
    site_paths,
    write_owned_site,
)

_PLACEHOLDER = '["__SLOPGATE_BIN__"]'
_BINARY_TEXT = strategies.text(
    alphabet=list("abcXYZ012/_-."), min_size=1, max_size=20
)
_TEXT_FRAGMENT = strategies.text(alphabet=list("abcXYZ012 _-."), max_size=20)
_MARKER_SUBSETS = strategies.frozensets(
    strategies.sampled_from(slopgate.installer._omp.OMP_OWNERSHIP_MARKERS)
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


def test_omp_agent_dir_uses_omp_override_or_home_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    configured = tmp_path / "profiles" / ".." / "active"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("OMP_AGENT_DIR", str(configured))
    assert slopgate.installer._omp.omp_agent_dir() == configured, (
        "a non-empty OMP_AGENT_DIR must be returned without path normalization"
    )
    monkeypatch.setenv("OMP_AGENT_DIR", "")
    assert slopgate.installer._omp.omp_agent_dir() == home / ".omp" / "agent", (
        "an empty OMP_AGENT_DIR must fall back to ~/.omp/agent"
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
    assert manifest_path.read_bytes() == (
        json.dumps(MANIFEST_PAYLOAD, indent=2) + "\n"
    ).encode(), "OMP manifest bytes must use canonical insertion order and formatting"
    assert not (index_path.parent / "config.json").exists(), (
        "OMP install must not create a config artifact"
    )


def test_omp_dry_run_lists_exact_artifacts_without_creating_directories(
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
    assert agent_dir.exists(), "rollback must preserve the pre-existing agent root"
    assert index_path.parent.parent.exists(), (
        "rollback must preserve the pre-existing extensions parent"
    )
    assert index_path.parent.exists(), "rollback must preserve the pre-existing package dir"
    assert not index_path.exists(), "rollback must remove only the partial artifact"


def test_omp_cross_site_failure_restores_bytes_modes_and_topology(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    project_root = tmp_path / "repo"
    project_root.mkdir()
    patch_install(monkeypatch, home)
    old_index = b"// retained prefix\n" + owned_index(str(tmp_path / "old-bin"))
    old_manifest = json.dumps(MANIFEST_PAYLOAD, separators=(",", ":")).encode()
    user_index, user_manifest = write_owned_site(
        home / ".omp" / "agent", OwnedSiteSeed(old_index, old_manifest)
    )
    project_index, project_manifest = site_paths(project_root / ".omp")
    fail_manifest_write(monkeypatch, project_manifest)
    assert slopgate.installer._omp.install_omp(
        scope="both", project_root=project_root
    ) == 1, "project failure must roll back the completed user install"
    assert (user_index.read_bytes(), user_manifest.read_bytes()) == (
        old_index,
        old_manifest,
    ), "cross-site rollback must restore differing owned bytes"
    assert (
        stat.S_IMODE(user_index.stat().st_mode),
        stat.S_IMODE(user_manifest.stat().st_mode),
    ) == (0o640, 0o600), "cross-site rollback must restore original modes"
    assert not (project_root / ".omp").exists(), (
        "cross-site rollback must restore the absent project topology"
    )
    residue = list(tmp_path.rglob("*.slopgate-bak-*")) + list(
        tmp_path.rglob(".slopgate-write-*.tmp")
    )
    assert residue == [], "OMP rollback must leave no backup or temporary residue"
    assert not project_index.exists(), "the failed project index must be removed"


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
