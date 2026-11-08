from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

import slopgate.installer
import slopgate.installer._omp
import slopgate.installer.native.claude_legacy
import slopgate.installer.native.entry
import slopgate.installer.native.marketplace.install
import slopgate.installer.native.marketplace.uninstall
from slopgate.constants import (
    INSTALL_SCOPE_BOTH,
    INSTALL_SCOPE_PROJECT,
    INSTALL_SCOPE_USER,
)
from slopgate.installer._shared import UnsafeInstallPathError
from slopgate.installer.native.marketplace.host import MarketplaceHost
from slopgate.installer.native.model import (
    LegacyRefusal,
    NativeRequest,
    Registration,
)
from slopgate.installer.native.omp import OmpMarketplaceHost
from slopgate.installer.native.omp_legacy import OmpLegacyCutover
from slopgate.installer.native.packages import PackagePlan, native_host_root
from tests.claude_installer_support import claude_harness
from tests.native.omp_fake import OMP_PLUGIN_ID, read_fake_state
from tests.omp_installer_support import (
    entries_for_scope,
    native_inventory,
    prepare_omp_sandbox,
    seed_legacy,
)


def _artifact_state(
    paths: tuple[Path, ...],
) -> tuple[tuple[bytes, int], ...]:
    return tuple(
        (path.read_bytes(), stat.S_IMODE(path.stat().st_mode)) for path in paths
    )


def _unsafe_cutover(
    _host: OmpMarketplaceHost, _request: NativeRequest
) -> OmpLegacyCutover:
    raise UnsafeInstallPathError("injected unsafe cutover path")


def _unsafe_preflight(_cutover: OmpLegacyCutover) -> None:
    raise UnsafeInstallPathError("injected unsafe preflight path")


@dataclass(frozen=True, slots=True)
class _PreflightObservation:
    status: int
    output: str
    manager_calls: object


def _unsafe_preflight_observation(
    boundary: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _PreflightObservation:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path)
    if boundary == "install":
        monkeypatch.setattr(OmpLegacyCutover, "preflight", _unsafe_preflight)
        status = slopgate.installer._omp.install_omp(
            scope=INSTALL_SCOPE_USER, project_root=sandbox.project_root
        )
    else:
        monkeypatch.setattr(OmpMarketplaceHost, "legacy_cutover", _unsafe_cutover)
        request = NativeRequest(False, (INSTALL_SCOPE_USER,), sandbox.project_root)
        status = (
            slopgate.installer.native.marketplace.uninstall.uninstall_marketplace_host(
                OmpMarketplaceHost(), request
            )
        )
    output = capsys.readouterr().out
    calls = read_fake_state(sandbox.state_path)["calls"]
    return _PreflightObservation(status, output, calls)


@pytest.mark.parametrize("boundary", ("install", "uninstall"))
def test_unsafe_preflight_errors_return_status_without_traceback(
    boundary: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed = _unsafe_preflight_observation(boundary, tmp_path, monkeypatch, capsys)

    assert observed.status == 1, "unsafe marketplace preflight must return status one"
    assert "injected unsafe" in observed.output, (
        "known path failures should be reported"
    )
    assert "Traceback" not in observed.output, (
        "known preflight failures must not escape"
    )
    assert observed.manager_calls == [], (
        "preflight failures must precede native manager mutations"
    )


def _inject_rollback_inventory_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    rollback_started = False
    original_remove = OmpLegacyCutover.remove

    def remove_after_mutation(cutover: OmpLegacyCutover, scope: str) -> int:
        nonlocal rollback_started
        status = original_remove(cutover, scope)
        if scope == INSTALL_SCOPE_PROJECT and status == 0:
            rollback_started = True
            return 1
        return status

    monkeypatch.setattr(OmpLegacyCutover, "remove", remove_after_mutation)
    original_registration = (
        slopgate.installer.native.marketplace.install.registration_for
    )

    def refuse_project_rollback_inventory(
        host: MarketplaceHost, scope: str, root: Path
    ) -> Registration | None:
        if rollback_started and scope == INSTALL_SCOPE_PROJECT:
            raise LegacyRefusal("injected malformed inventory during rollback")
        return original_registration(host, scope, root)

    monkeypatch.setattr(
        slopgate.installer.native.marketplace.install,
        "registration_for",
        refuse_project_rollback_inventory,
    )


@dataclass(frozen=True, slots=True)
class _RollbackRefusalObservation:
    status: int
    output: str
    user_compensation_called: bool
    user_registration_count: int
    project_registration_count: int
    legacy_restored: bool
    staging_kept: bool


def _rollback_refusal_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _RollbackRefusalObservation:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path)
    user_paths = seed_legacy(sandbox, INSTALL_SCOPE_USER)
    project_paths = seed_legacy(sandbox, INSTALL_SCOPE_PROJECT)
    legacy_files = user_paths + project_paths
    legacy_before = _artifact_state(legacy_files)
    _inject_rollback_inventory_refusal(monkeypatch)
    status = slopgate.installer._omp.install_omp(
        scope=INSTALL_SCOPE_BOTH, project_root=sandbox.project_root
    )
    output = capsys.readouterr().out
    calls = cast(list[list[str]], read_fake_state(sandbox.state_path)["calls"])
    inventory = native_inventory(sandbox, sandbox.project_root)
    return _RollbackRefusalObservation(
        status,
        output,
        [
            "plugin",
            "uninstall",
            "--scope",
            INSTALL_SCOPE_USER,
            OMP_PLUGIN_ID,
        ]
        in calls,
        len(entries_for_scope(inventory, INSTALL_SCOPE_USER)),
        len(entries_for_scope(inventory, INSTALL_SCOPE_PROJECT)),
        _artifact_state(legacy_files) == legacy_before,
        native_host_root("omp").exists(),
    )


def test_legacy_refusal_during_rollback_continues_compensation_and_restores_legacy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed = _rollback_refusal_observation(tmp_path, monkeypatch, capsys)

    assert observed.status == 1, (
        "rollback inventory refusal must produce a failed install status"
    )
    assert "Incomplete rollback:" in observed.output, (
        "incomplete compensation must be explicit"
    )
    assert "injected malformed inventory" in observed.output, (
        "rollback diagnostics must include the inventory refusal"
    )
    assert "Traceback" not in observed.output, (
        "known rollback errors must not escape as tracebacks"
    )
    assert observed.user_compensation_called, (
        "user-scope compensation must run after project-scope inventory refusal"
    )
    assert observed.user_registration_count == 0, (
        "later user-scope compensation must remove its native registration"
    )
    assert observed.project_registration_count == 1, (
        "the injected project inventory refusal should be reported as incomplete"
    )
    assert observed.legacy_restored, (
        "all removed legacy artifacts must be restored despite inventory refusal"
    )
    assert observed.staging_kept, (
        "staged payload must stay while a native registration remains"
    )


def _raise_unsafe_after_anchor(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_capture(_cutover: OmpLegacyCutover) -> None:
        raise UnsafeInstallPathError("injected failure after anchor creation")

    monkeypatch.setattr(OmpLegacyCutover, "capture", fail_capture)


def _raise_unsafe_after_staging(monkeypatch: pytest.MonkeyPatch) -> None:
    original_write = slopgate.installer.native.marketplace.install.write_staging

    def fail_after_write(plan: PackagePlan) -> None:
        original_write(plan)
        raise UnsafeInstallPathError("injected failure after staging write")

    monkeypatch.setattr(
        slopgate.installer.native.marketplace.install, "write_staging", fail_after_write
    )


@dataclass(frozen=True, slots=True)
class _UnsafeTransactionObservation:
    initially_unstaged: bool
    status: int
    output: str
    project_anchor_exists: bool
    staging_exists: bool


def _unsafe_transaction_observation(
    failure_point: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _UnsafeTransactionObservation:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path)
    staging_root = native_host_root("omp")
    initially_unstaged = not staging_root.exists()
    if failure_point == "after_anchor":
        _raise_unsafe_after_anchor(monkeypatch)
    else:
        _raise_unsafe_after_staging(monkeypatch)
    status = slopgate.installer._omp.install_omp(
        scope=INSTALL_SCOPE_PROJECT, project_root=sandbox.project_root
    )
    output = capsys.readouterr().out
    return _UnsafeTransactionObservation(
        initially_unstaged,
        status,
        output,
        (sandbox.project_root / ".omp").exists(),
        staging_root.exists(),
    )


@pytest.mark.parametrize(
    "failure_point",
    ("after_anchor", "after_staging"),
    ids=("after-anchor-creation", "after-committed-staging-write"),
)
def test_unsafe_install_path_error_rolls_back_omp_transaction(
    failure_point: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed = _unsafe_transaction_observation(
        failure_point, tmp_path, monkeypatch, capsys
    )

    assert observed.initially_unstaged, (
        "the OMP test harness starts without staged files"
    )
    assert observed.status == 1, "unsafe transaction errors must return status one"
    assert "Traceback" not in observed.output, (
        "unsafe transaction errors must not escape as tracebacks"
    )
    assert not observed.project_anchor_exists, (
        "rollback must remove the transaction-created project anchor"
    )
    assert not observed.staging_exists, (
        "rollback must remove transaction-created staging files and directories"
    )


def test_claude_public_install_returns_status_for_unsafe_transaction_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    harness = claude_harness(tmp_path, monkeypatch)
    monkeypatch.setattr(
        slopgate.installer.native.entry, "find_binary", lambda: "slopgate-test"
    )

    def fail_capture(
        _cutover: slopgate.installer.native.claude_legacy.ClaudeLegacyCutover,
    ) -> None:
        raise UnsafeInstallPathError("injected Claude transaction error")

    monkeypatch.setattr(
        slopgate.installer.native.claude_legacy.ClaudeLegacyCutover,
        "capture",
        fail_capture,
    )
    status = slopgate.installer.install_claude(
        scope=INSTALL_SCOPE_USER, project_root=harness.project
    )
    output = capsys.readouterr().out

    assert status == 1, "Claude's public install path must return status one"
    assert "injected Claude transaction error" in output, (
        "Claude's public install path must report the transaction failure"
    )
    assert "Traceback" not in output, (
        "Claude transaction errors must not escape as tracebacks"
    )
