from __future__ import annotations

import shutil
from pathlib import Path
from typing import cast

import pytest
from hypothesis import given, settings, strategies

from slopgate.constants import INSTALL_SCOPE_PROJECT, INSTALL_SCOPE_USER
from slopgate.installer.native.marketplace.state import (
    Preflight,
    compensation_commands,
    marketplace_command,
    preflight,
    registration_for,
    run_checked,
    scope_commands,
    verification_problem,
)
from slopgate.installer.native.model import NativeRequest, Registration
from tests.native.marketplace_support import (
    FAKE_EXECUTABLE,
    FakeMarketplaceCommands,
    FakeMarketplaceHost,
    RecordingCutover,
    activate_fake_manager,
    marketplace_command_count,
)

PROPERTY_EXAMPLES = 32
EXPECTED_VERSION = "2.4.2+local.testdigest"
PREFLIGHT_CASES = strategies.tuples(
    strategies.sampled_from((INSTALL_SCOPE_USER, INSTALL_SCOPE_PROJECT)),
    strategies.booleans(),
    strategies.booleans(),
    strategies.booleans(),
    strategies.booleans(),
    strategies.booleans(),
)
VERIFICATION_CASES = strategies.tuples(
    strategies.booleans(),
    strategies.booleans(),
    strategies.booleans(),
    strategies.one_of(strategies.none(), strategies.booleans()),
)


def _preflight_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: tuple[str, bool, bool, bool, bool, bool],
) -> tuple[object, bool]:
    (
        scope,
        root_exists,
        manager_available,
        anchor_problem,
        collision,
        cutover_refusal,
    ) = case
    state_path, _ = activate_fake_manager(tmp_path, monkeypatch)
    root = tmp_path / "project"
    if root.exists():
        shutil.rmtree(root)
    if root_exists:
        root.mkdir()
    host = FakeMarketplaceHost(state_path, root)
    host.seed_state({"marketplaces": {}, "registrations": []})
    if not manager_available:
        host.executable = "native-manager-not-on-path"
    if anchor_problem:
        host.project_issue = "test project anchor refusal"
    if collision:
        host.seed_state(
            {
                "marketplaces": {"slopgate-runtime": str(tmp_path / "foreign-source")},
                "registrations": [],
            }
        )
    request = NativeRequest(False, (scope,), root)
    cutover = cast(RecordingCutover, host.legacy_cutover(request))
    cutover.refuse = cutover_refusal
    observed = preflight(host, host.build_plan("binary"), request, cutover)
    accepted = (
        root_exists and manager_available and not collision and not cutover_refusal
    )
    accepted = accepted and (scope != INSTALL_SCOPE_PROJECT or not anchor_problem)
    return observed, accepted


def _isolated_preflight_case(
    tmp_path_factory: pytest.TempPathFactory,
    case: tuple[str, bool, bool, bool, bool, bool],
) -> tuple[object, bool]:
    tmp_path = tmp_path_factory.mktemp("marketplace-preflight")
    with pytest.MonkeyPatch.context() as monkeypatch:
        return _preflight_case(tmp_path, monkeypatch, case)


@settings(max_examples=PROPERTY_EXAMPLES, deadline=None)
@given(case=PREFLIGHT_CASES)
def test_preflight_decision_table_refuses_unsafe_inputs(
    tmp_path_factory: pytest.TempPathFactory,
    case: tuple[str, bool, bool, bool, bool, bool],
) -> None:
    observed, accepted = _isolated_preflight_case(tmp_path_factory, case)

    assert (observed is not None) == accepted, (
        "preflight should accept exactly existing roots with available managers, matching sources, safe anchors, and clean cutovers"
    )


@settings(max_examples=PROPERTY_EXAMPLES, deadline=None)
@given(case=VERIFICATION_CASES)
def test_verification_problem_matches_registration_state_table(
    case: tuple[bool, bool, bool, bool | None],
) -> None:
    current_present, current_matches, prior_present, prior_enabled = case
    current = (
        Registration(
            "plugin",
            INSTALL_SCOPE_USER,
            EXPECTED_VERSION if current_matches else "old",
            True,
        )
        if current_present
        else None
    )
    prior = (
        Registration("plugin", INSTALL_SCOPE_USER, "old", prior_enabled)
        if prior_present
        else None
    )
    problem = verification_problem(current, prior, EXPECTED_VERSION)
    verified = (
        current is not None
        and current.version == EXPECTED_VERSION
        and (prior is None or prior.enabled is None or current.enabled == prior.enabled)
    )

    assert (problem is None) == verified, (
        "verification should succeed exactly for the expected version and preserved recorded state"
    )
    assert (current is None) == (problem == "no registration found"), (
        "an absent registration should be the unique missing-entry diagnostic"
    )


def test_registration_for_matches_exact_scope_and_project(tmp_path: Path) -> None:
    root = tmp_path / "project"
    other = tmp_path / "other"
    root.mkdir()
    other.mkdir()
    host = FakeMarketplaceHost(tmp_path / "state.json", root)
    host.seed_state(
        {
            "marketplaces": {},
            "registrations": [
                {
                    "scope": INSTALL_SCOPE_PROJECT,
                    "project": str(other),
                    "version": "v1",
                    "enabled": True,
                },
                {
                    "scope": INSTALL_SCOPE_PROJECT,
                    "project": str(root),
                    "version": "v2",
                    "enabled": False,
                },
            ],
        }
    )

    found = registration_for(host, INSTALL_SCOPE_PROJECT, root)

    assert found is not None and found.version == "v2", (
        "project registration lookup should exclude registrations owned by another root"
    )
    assert found.enabled is False, (
        "exact project lookup should preserve recorded disabled state"
    )


def test_run_checked_returns_native_stdout_and_executes_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path, log_path = activate_fake_manager(tmp_path, monkeypatch)
    root = tmp_path / "project"
    root.mkdir()
    host = FakeMarketplaceHost(state_path, root)
    host.seed_state(
        {"marketplaces": {"slopgate-runtime": str(tmp_path)}, "registrations": []}
    )

    output = run_checked(host, host.commands.marketplace_update(), root)

    assert output == "", (
        "successful marketplace update should return the native stdout unchanged"
    )
    assert marketplace_command_count(log_path) == 1, (
        "checked native commands should cross the real fake-manager boundary"
    )


def _marketplace_command_observation(
    tmp_path: Path,
) -> tuple[tuple[object, ...], tuple[object, ...]]:
    host = FakeMarketplaceHost(tmp_path / "state.json", tmp_path)
    plan = host.build_plan("binary")
    commands = FakeMarketplaceCommands()
    absent = Preflight(False, False, {})
    stale = Preflight(True, False, {})
    current = Preflight(True, True, {})
    observed = (
        marketplace_command(host, plan, absent),
        marketplace_command(host, plan, stale),
        marketplace_command(host, plan, current),
    )
    expected = (
        commands.marketplace_add(plan.entry_root),
        commands.marketplace_update(),
        None,
    )
    return observed, expected


def _scope_command_observation(
    tmp_path: Path,
) -> tuple[tuple[object, ...], tuple[object, ...]]:
    host = FakeMarketplaceHost(tmp_path / "state.json", tmp_path)
    prior = Registration(host.plugin_id, INSTALL_SCOPE_USER, "old", False)
    current = Registration(host.plugin_id, INSTALL_SCOPE_USER, EXPECTED_VERSION, False)
    observed = (
        scope_commands(host, INSTALL_SCOPE_USER, (None, EXPECTED_VERSION)),
        scope_commands(host, INSTALL_SCOPE_USER, (prior, EXPECTED_VERSION)),
        compensation_commands(host, INSTALL_SCOPE_USER, (prior, current)),
        compensation_commands(host, INSTALL_SCOPE_PROJECT, (None, current)),
    )
    expected = (
        [[FAKE_EXECUTABLE, "install", INSTALL_SCOPE_USER]],
        [[FAKE_EXECUTABLE, "replace", INSTALL_SCOPE_USER]],
        [[FAKE_EXECUTABLE, "replace", INSTALL_SCOPE_USER]],
        [[FAKE_EXECUTABLE, "uninstall", INSTALL_SCOPE_PROJECT]],
    )
    return observed, expected


def test_marketplace_command_planning_preserves_prior_state(
    tmp_path: Path,
) -> None:
    observed, expected = _marketplace_command_observation(tmp_path)

    assert observed == expected, (
        "marketplace planning should add once, refresh stale catalogs, and skip current catalogs"
    )


def test_scope_command_planning_preserves_prior_registration(
    tmp_path: Path,
) -> None:
    observed, expected = _scope_command_observation(tmp_path)

    assert observed == expected, (
        "scope planning should install, replace, and compensate only the required registration"
    )


def test_fake_host_interface_is_structurally_bound_to_marketplace_commands() -> None:
    commands = FakeMarketplaceCommands()
    assert commands.marketplace_remove() == [FAKE_EXECUTABLE, "marketplace-remove"], (
        "the fake host command contract should expose an exact marketplace removal vector"
    )


def test_scope_planning_avoids_noop_and_restores_missing_prior_registration(
    tmp_path: Path,
) -> None:
    host = FakeMarketplaceHost(tmp_path / "state.json", tmp_path)
    current = Registration(
        host.plugin_id,
        INSTALL_SCOPE_USER,
        EXPECTED_VERSION,
        True,
    )

    observed = (
        scope_commands(host, INSTALL_SCOPE_USER, (current, EXPECTED_VERSION)),
        compensation_commands(host, INSTALL_SCOPE_USER, (current, None)),
        compensation_commands(host, INSTALL_SCOPE_PROJECT, (None, None)),
    )

    assert observed == (
        [],
        [[FAKE_EXECUTABLE, "install", INSTALL_SCOPE_USER]],
        [],
    ), (
        "scope planning should skip current registrations and restore missing prior state"
    )
