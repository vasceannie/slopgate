"""Install-suite dry runs reject malformed native inventories without mutation."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

import slopgate.installer
from slopgate.installer.native.omp import OMP_PLUGIN_ID
from tests.native.hosts import FakeHosts, tree_digest
from tests.native.omp_fake import read_fake_state


@dataclass(frozen=True, slots=True)
class _DryRunObservation:
    status: int
    output: str
    state_before: bytes
    state_after: bytes
    staging_before: str
    staging_after: str
    home_before: str
    home_after: str
    omp_calls: list[list[str]]
    mutating_calls: list[str]


def _unexpected_scope_dry_run(
    native_hosts: FakeHosts, capsys: pytest.CaptureFixture[str]
) -> _DryRunObservation:
    state = read_fake_state(native_hosts.omp_state_path)
    state["registrations"] = [
        {
            "id": OMP_PLUGIN_ID,
            "scope": "unexpected",
            "version": "1.0.0",
            "enabled": True,
        }
    ]
    native_hosts.omp_state_path.write_text(json.dumps(state), encoding="utf-8")
    state_before = native_hosts.omp_state_path.read_bytes()
    staging_before = native_hosts.staging_digest()
    home_before = tree_digest(native_hosts.home)
    status = slopgate.installer.install_suite(
        slopgate.installer.SuiteInstallOptions(
            dry_run=True,
            with_autoupdate=False,
        )
    )
    output = capsys.readouterr().out
    return _DryRunObservation(
        status,
        output,
        state_before,
        native_hosts.omp_state_path.read_bytes(),
        staging_before,
        native_hosts.staging_digest(),
        home_before,
        tree_digest(native_hosts.home),
        native_hosts.omp_calls(),
        native_hosts.mutating_calls(),
    )


def test_install_suite_dry_run_rejects_unexpected_omp_scope_without_writing(
    native_hosts: FakeHosts, capsys: pytest.CaptureFixture[str]
) -> None:
    observed = _unexpected_scope_dry_run(native_hosts, capsys)

    assert observed.status == 1, "malformed OMP inventory must fail suite preflight"
    assert (
        f"Malformed OMP registration for {OMP_PLUGIN_ID}: unsupported scope 'unexpected'"
        in observed.output
    ), "suite dry-run must surface the product's malformed-scope refusal"
    assert observed.state_after == observed.state_before, (
        "malformed inventory preflight must preserve fake OMP state bytes"
    )
    assert observed.staging_after == observed.staging_before, (
        "malformed inventory preflight must preserve native staging"
    )
    assert observed.home_after == observed.home_before, (
        "malformed inventory preflight must not alter the isolated home tree"
    )
    assert observed.omp_calls == [], (
        "invalid-scope preflight must not invoke mutating OMP manager commands"
    )
    assert observed.mutating_calls == [], (
        "suite dry-run must not mutate any native host registration"
    )
