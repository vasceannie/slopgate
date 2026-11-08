from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

import slopgate.installer
import slopgate.installer._omp
from slopgate.constants import (
    INSTALL_SCOPE_BOTH,
    INSTALL_SCOPE_PROJECT,
    INSTALL_SCOPE_USER,
)
from tests.native.omp_fake import read_fake_state
from slopgate.installer.native.packages import native_host_root
from tests.omp_installer_support import (
    OmpSandbox,
    entries_for_scope,
    native_inventory,
    prepare_omp_sandbox,
    seed_legacy,
    seed_marketplace_collision,
    seed_unrelated_registration,
)


@dataclass(frozen=True, slots=True)
class _CollisionOutcome:
    status: int
    legacy: tuple[Path, ...]
    legacy_before: tuple[bytes, ...]


def _attempt_foreign_marketplace_install(
    sandbox: OmpSandbox, tmp_path: Path
) -> _CollisionOutcome:
    legacy = seed_legacy(sandbox, INSTALL_SCOPE_USER)
    before = tuple(path.read_bytes() for path in legacy)
    foreign_source = tmp_path / "foreign marketplace"
    foreign_source.mkdir()
    seed_marketplace_collision(sandbox, foreign_source)
    status = slopgate.installer._omp.install_omp()
    return _CollisionOutcome(status, legacy, before)


@dataclass(frozen=True, slots=True)
class _UninstallOutcome:
    install_status: int
    uninstall_status: int
    user_entries: list[dict[str, object]]
    project_entries: list[dict[str, object]]
    unrelated: list[dict[str, object]]


def _install_both_scopes_then_uninstall_user(
    sandbox: OmpSandbox,
) -> _UninstallOutcome:
    seed_unrelated_registration(sandbox)
    install_status = slopgate.installer._omp.install_omp(
        scope=INSTALL_SCOPE_BOTH, project_root=sandbox.project_root
    )
    uninstall_status = slopgate.installer.uninstall_platform(
        "omp", install_scope=INSTALL_SCOPE_USER, project_root=sandbox.project_root
    )
    inventory = native_inventory(sandbox, sandbox.project_root)
    unrelated = [
        plugin
        for plugin in cast(list[dict[str, object]], inventory["marketplace"])
        if plugin.get("id") == "unrelated-package@other-marketplace"
    ]
    return _UninstallOutcome(
        install_status,
        uninstall_status,
        entries_for_scope(inventory, INSTALL_SCOPE_USER),
        entries_for_scope(inventory, INSTALL_SCOPE_PROJECT),
        unrelated,
    )


def test_install_omp_refuses_unknown_marketplace_source_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path)
    outcome = _attempt_foreign_marketplace_install(sandbox, tmp_path)
    assert outcome.status == 1, (
        "OMP should refuse a marketplace-name collision with another source"
    )
    assert (
        tuple(path.read_bytes() for path in outcome.legacy) == outcome.legacy_before
    ), (
        "marketplace collision refusal should leave the legacy enforcement byte-identical"
    )
    assert read_fake_state(sandbox.state_path).get("calls") == [], (
        "source collision should be refused before any native mutation"
    )


def test_uninstall_omp_selected_scope_preserves_other_and_unrelated_plugins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path)
    outcome = _install_both_scopes_then_uninstall_user(sandbox)
    assert outcome.install_status == outcome.uninstall_status == 0, (
        "selected-scope OMP install and uninstall should both complete"
    )
    assert outcome.user_entries == [], (
        "user-scope uninstall should remove only that registration"
    )
    assert len(outcome.project_entries) == 1, (
        "project-scope OMP registration should remain installed"
    )
    assert len(outcome.unrelated) == 1, (
        "unrelated native project registrations should remain untouched"
    )
    stage_root = native_host_root("omp")
    assert stage_root.exists(), "uninstall should retain shared OMP marketplace staging"
