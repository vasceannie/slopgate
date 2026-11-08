from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from hypothesis import given, settings, strategies

import slopgate
import slopgate.installer._omp
import slopgate.installer._shared
from slopgate.constants import (
    INSTALL_SCOPE_BOTH,
    INSTALL_SCOPE_PROJECT,
    INSTALL_SCOPE_USER,
)
from tests.native.omp_fake import OMP_PLUGIN_ID, read_fake_state
from slopgate.installer.native.packages import native_host_root
from tests.omp_installer_support import (
    REFRESHED_BINARY,
    OmpSandbox,
    entries_for_scope,
    native_inventory,
    prepare_omp_sandbox,
    seed_legacy,
)

_UPGRADED_VERSION = "99.0.0"


def _staged_payload() -> tuple[dict[str, object], Path, Path]:
    stage_root = native_host_root("omp") / "marketplace"
    catalog = cast(
        dict[str, object],
        json.loads((stage_root / ".omp-plugin" / "marketplace.json").read_text()),
    )
    plugin = cast(dict[str, object], cast(list[object], catalog["plugins"])[0])
    payload_root = stage_root / str(plugin["source"]).removeprefix("./")
    return catalog, payload_root, payload_root / "index.ts"


@dataclass(frozen=True, slots=True)
class _MigrationOutcome:
    status: int
    repeat_status: int
    user_entries: list[dict[str, object]]
    project_entries: list[dict[str, object]]
    legacy_paths: tuple[Path, ...]
    calls_before: object


def _install_both_scopes_twice(sandbox: OmpSandbox) -> _MigrationOutcome:
    legacy_user = seed_legacy(sandbox, INSTALL_SCOPE_USER)
    legacy_project = seed_legacy(sandbox, INSTALL_SCOPE_PROJECT)
    status = slopgate.installer._omp.install_omp(
        scope=INSTALL_SCOPE_BOTH, project_root=sandbox.project_root
    )
    inventory = native_inventory(sandbox, sandbox.project_root)
    calls_before = read_fake_state(sandbox.state_path).get("calls")
    repeat_status = slopgate.installer._omp.install_omp(
        scope=INSTALL_SCOPE_BOTH, project_root=sandbox.project_root
    )
    return _MigrationOutcome(
        status,
        repeat_status,
        entries_for_scope(inventory, INSTALL_SCOPE_USER),
        entries_for_scope(inventory, INSTALL_SCOPE_PROJECT),
        legacy_user + legacy_project,
        calls_before,
    )


@dataclass(frozen=True, slots=True)
class _RefreshOutcome:
    initial_status: int
    refresh_status: int
    entry: dict[str, object]
    calls: list[list[str]]
    staged_index: Path


def _refresh_changed_invocation(
    sandbox: OmpSandbox, monkeypatch: pytest.MonkeyPatch
) -> _RefreshOutcome:
    initial_status = slopgate.installer._omp.install_omp(
        scope=INSTALL_SCOPE_PROJECT, project_root=sandbox.project_root
    )
    subprocess.run(
        [
            str(sandbox.launcher),
            "plugin",
            "disable",
            "--scope",
            INSTALL_SCOPE_PROJECT,
            OMP_PLUGIN_ID,
        ],
        cwd=sandbox.project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: REFRESHED_BINARY
    )
    refresh_status = slopgate.installer._omp.install_omp(
        scope=INSTALL_SCOPE_PROJECT, project_root=sandbox.project_root
    )
    entry = entries_for_scope(
        native_inventory(sandbox, sandbox.project_root), INSTALL_SCOPE_PROJECT
    )[0]
    calls = cast(list[list[str]], read_fake_state(sandbox.state_path)["calls"])
    _, _, staged_index = _staged_payload()
    return _RefreshOutcome(initial_status, refresh_status, entry, calls, staged_index)


@dataclass(frozen=True, slots=True)
class _VersionBumpOutcome:
    refresh_status: int
    old_version: str
    old_payload: Path
    old_index_bytes: bytes
    new_version: object
    new_payload: Path
    new_index_bytes: bytes
    package_version: object
    registered_version: object


def _upgrade_staged_version(
    sandbox: OmpSandbox, monkeypatch: pytest.MonkeyPatch
) -> _VersionBumpOutcome:
    old_catalog, old_payload, old_index = _staged_payload()
    old_plugin = cast(dict[str, object], cast(list[object], old_catalog["plugins"])[0])
    old_version = str(old_plugin["version"])
    old_index_bytes = old_index.read_bytes()
    monkeypatch.setattr(slopgate, "__version__", _UPGRADED_VERSION)
    refresh_status = slopgate.installer._omp.install_omp()
    new_catalog, new_payload, new_index = _staged_payload()
    new_plugin = cast(dict[str, object], cast(list[object], new_catalog["plugins"])[0])
    package = cast(
        dict[str, object], json.loads((new_payload / "package.json").read_text())
    )
    registration = entries_for_scope(
        native_inventory(sandbox, sandbox.project_root), INSTALL_SCOPE_USER
    )[0]
    return _VersionBumpOutcome(
        refresh_status,
        old_version,
        old_payload,
        old_index_bytes,
        new_plugin["version"],
        new_payload,
        new_index.read_bytes(),
        package["version"],
        registration["version"],
    )


@settings(deadline=None)
@given(binary=strategies.text(alphabet=list("abcXYZ012/_-."), min_size=1, max_size=20))
def test_render_omp_extension_replaces_only_argv_placeholder(binary: str) -> None:
    template = 'prefix ["__SLOPGATE_BIN__"] suffix'
    rendered = slopgate.installer._omp.render_omp_extension(template, binary)
    expected = f"prefix {json.dumps([binary])} suffix"
    assert rendered == expected, (
        "OMP rendering should replace only the argv placeholder"
    )


def test_omp_agent_dir_uses_absolute_pi_agent_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    active = tmp_path / "profiles" / "active"
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(active))
    assert slopgate.installer._omp.omp_agent_dir() == active, (
        "an absolute PI_CODING_AGENT_DIR should select the legacy agent root"
    )


def test_install_omp_migrates_legacy_both_scopes_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path)
    outcome = _install_both_scopes_twice(sandbox)
    assert outcome.status == 0, (
        "both-scope OMP install should register the native plugin"
    )
    assert {
        entry["scope"] for entry in outcome.user_entries + outcome.project_entries
    } == {
        INSTALL_SCOPE_USER,
        INSTALL_SCOPE_PROJECT,
    }, "native inventory should expose exactly the selected user/project registrations"
    assert outcome.user_entries[0].get("version") == outcome.project_entries[0].get(
        "version"
    ), "both native scopes should use one staged package version"
    assert all(not path.exists() for path in outcome.legacy_paths), (
        "legacy index and manifest should be retired only after registration verification"
    )
    assert sandbox.project_root.name == "project with space", (
        "native project scope should retain the requested path containing spaces"
    )
    assert outcome.repeat_status == 0, (
        "reinstalling a current OMP registration should succeed"
    )
    assert read_fake_state(sandbox.state_path).get("calls") == outcome.calls_before, (
        "an idempotent reinstall should not issue native mutations"
    )


def test_install_omp_changed_invocation_force_refresh_preserves_disabled_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path)
    outcome = _refresh_changed_invocation(sandbox, monkeypatch)
    assert outcome.initial_status == 0 and outcome.refresh_status == 0, (
        "initial install and explicit changed-invocation refresh should succeed"
    )
    assert outcome.entry.get("enabled") is False, (
        "a force refresh must preserve OMP's explicitly disabled native state"
    )
    assert REFRESHED_BINARY.encode() in outcome.staged_index.read_bytes(), (
        "refresh should stage the newly rendered Slopgate invocation"
    )
    assert any("--force" in call and OMP_PLUGIN_ID in call for call in outcome.calls), (
        "changed OMP payloads should be replaced through the native --force command"
    )


def test_install_omp_version_only_upgrade_creates_matching_new_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path)
    assert slopgate.installer._omp.install_omp() == 0, (
        "initial native OMP install should succeed before the package version changes"
    )
    outcome = _upgrade_staged_version(sandbox, monkeypatch)
    assert outcome.refresh_status == 0, (
        "version-only OMP upgrade should refresh the native package"
    )
    assert (
        outcome.new_version == outcome.package_version == outcome.registered_version
    ), (
        "catalog, embedded package manifest, and native inventory should agree on version"
    )
    assert outcome.new_version != outcome.old_version, (
        "changing only Slopgate's base version should create a distinct package version"
    )
    assert outcome.new_payload != outcome.old_payload, (
        "version-only upgrades should use a new snapshot path"
    )
    assert outcome.new_index_bytes == outcome.old_index_bytes, (
        "version-only upgrades should leave the rendered extension body unchanged"
    )
