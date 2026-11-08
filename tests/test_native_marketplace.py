from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings, strategies

from slopgate.constants import INSTALL_SCOPE_PROJECT, INSTALL_SCOPE_USER
from slopgate.installer.native.marketplace.install import install_marketplace_host
from slopgate.installer.native.marketplace.uninstall import uninstall_marketplace_host
from slopgate.installer.native.model import NativeRequest
from slopgate.installer.native.packages import (
    owned_staging_present,
    write_staging,
)
from tests.native.marketplace_support import (
    FAKE_MARKETPLACE_NAME,
    FakeMarketplaceHost,
    activate_fake_manager,
    marketplace_command_count,
    read_marketplace_state,
)

BINARY = "slopgate-test-binary"
REFRESHED_BINARY = "slopgate-refreshed-binary"
PROPERTY_EXAMPLES = 12
BINARY_TEXT = strategies.text(
    alphabet=strategies.characters(whitelist_categories=("Ll", "Lu", "Nd")),
    min_size=1,
    max_size=12,
)
SCOPE_VALUES = strategies.sampled_from((INSTALL_SCOPE_USER, INSTALL_SCOPE_PROJECT))
USER_AND_PROJECT = (INSTALL_SCOPE_USER, INSTALL_SCOPE_PROJECT)
INSTALL_CASES = strategies.tuples(SCOPE_VALUES, BINARY_TEXT)


def _host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[FakeMarketplaceHost, Path, Path]:
    state_path, log_path = activate_fake_manager(tmp_path, monkeypatch)
    project = tmp_path / "project"
    project.mkdir()
    return FakeMarketplaceHost(state_path, project), project, log_path


def _registration_scopes(host: FakeMarketplaceHost, project: Path) -> set[str]:
    return {registration.scope for registration in host.registrations(project)}


def _install_matches_requested_scope(
    tmp_path_factory: pytest.TempPathFactory, scope: str, binary: str
) -> bool:
    root = tmp_path_factory.mktemp("native-marketplace")
    with pytest.MonkeyPatch.context() as monkeypatch:
        host, project, _ = _host(root, monkeypatch)
        request = NativeRequest(False, (scope,), project)
        status = install_marketplace_host(host, request, binary)
        registrations = host.registrations(project)
        plan = host.build_plan(binary)
        registration = registrations[0] if registrations else None
        expected_project = project if scope == INSTALL_SCOPE_PROJECT else None
        observed = (
            status,
            len(registrations),
            registration.identity if registration is not None else None,
            registration.scope if registration is not None else None,
            registration.version if registration is not None else None,
            registration.project if registration is not None else None,
        )
        return observed == (
            0,
            1,
            host.plugin_id,
            scope,
            plan.version,
            expected_project,
        )


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _install_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, int, set[str], list[str], bool, bool, bool]:
    host, project, log_path = _host(tmp_path, monkeypatch)
    request = NativeRequest(False, USER_AND_PROJECT, project)
    first_status = install_marketplace_host(host, request, BINARY)
    first_count = marketplace_command_count(log_path)
    second_status = install_marketplace_host(host, request, BINARY)
    observed = (
        first_status,
        second_status,
        _registration_scopes(host, project),
        host.cutovers[-1].removed,
        marketplace_command_count(log_path) == first_count,
        FAKE_MARKETPLACE_NAME in host.marketplace_sources(project),
        owned_staging_present(FakeMarketplaceHost.platform),
    )
    return observed


def _failed_refresh_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, set[str], dict[str, str], bool, int, bool]:
    host, project, _ = _host(tmp_path, monkeypatch)
    original_plan = host.build_plan(BINARY)
    write_staging(original_plan)
    before = _tree_bytes(original_plan.entry_root)
    monkeypatch.setenv("FAKE_MARKETPLACE_FAIL_MATCH", "install project")

    status = install_marketplace_host(
        host, NativeRequest(False, USER_AND_PROJECT, project), REFRESHED_BINARY
    )
    after = _tree_bytes(original_plan.entry_root)
    return (
        status,
        _registration_scopes(host, project),
        host.marketplace_sources(project),
        before == after,
        host.cutovers[-1].restored,
        owned_staging_present(FakeMarketplaceHost.platform),
    )


def _dry_run_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, dict[str, object], dict[str, object], bool, int]:
    host, project, log_path = _host(tmp_path, monkeypatch)
    before = read_marketplace_state(host.state_path)
    plan = host.build_plan(BINARY)
    status = install_marketplace_host(
        host, NativeRequest(True, USER_AND_PROJECT, project), BINARY
    )
    return (
        status,
        read_marketplace_state(host.state_path),
        before,
        plan.entry_root.exists(),
        marketplace_command_count(log_path),
    )


def _collision_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, str, bool, int]:
    host, project, log_path = _host(tmp_path, monkeypatch)
    collision = tmp_path / "foreign-marketplace"
    collision.mkdir()
    host.seed_state(
        {
            "marketplaces": {FAKE_MARKETPLACE_NAME: str(collision)},
            "registrations": [],
        }
    )
    plan = host.build_plan(BINARY)
    status = install_marketplace_host(
        host, NativeRequest(False, USER_AND_PROJECT, project), BINARY
    )
    return (
        status,
        host.marketplace_sources(project)[FAKE_MARKETPLACE_NAME],
        plan.entry_root.exists(),
        marketplace_command_count(log_path),
    )


def _selected_uninstall_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, int, set[str], bool, bool, bool]:
    host, project, _ = _host(tmp_path, monkeypatch)
    request = NativeRequest(False, USER_AND_PROJECT, project)
    install_status = install_marketplace_host(host, request, BINARY)
    plan = host.build_plan(BINARY)
    before = _tree_bytes(plan.entry_root)
    status = uninstall_marketplace_host(
        host, NativeRequest(False, (INSTALL_SCOPE_PROJECT,), project)
    )
    return (
        install_status,
        status,
        _registration_scopes(host, project),
        FAKE_MARKETPLACE_NAME in host.marketplace_sources(project),
        before == _tree_bytes(plan.entry_root),
        owned_staging_present(FakeMarketplaceHost.platform),
    )


def test_marketplace_install_integration_registers_both_scopes_idempotently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = _install_twice(tmp_path, monkeypatch)

    assert observed == (
        0,
        0,
        set(USER_AND_PROJECT),
        list(USER_AND_PROJECT),
        True,
        True,
        True,
    ), "fresh install should register both scopes and rerun without native mutations"


def test_marketplace_install_integration_rolls_back_registration_and_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = _failed_refresh_rollback(tmp_path, monkeypatch)

    assert observed == (1, set(), {}, True, 1, True), (
        "failed project registration should restore prior staging and legacy state"
    )


def test_marketplace_dry_run_does_not_mutate_inventory_or_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status, after, before, staged, command_count = _dry_run_observations(
        tmp_path, monkeypatch
    )

    assert (status, after, staged, command_count) == (0, before, False, 0), (
        "dry run should preserve native inventory, create no staging files, and launch no mutating commands"
    )


def test_marketplace_source_collision_is_refused_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status, source, staged, command_count = _collision_observations(
        tmp_path, monkeypatch
    )

    assert (status, Path(source).name, staged, command_count) == (
        1,
        "foreign-marketplace",
        False,
        0,
    ), "a marketplace name with a foreign source should be refused before mutation"


def test_marketplace_uninstall_keeps_shared_catalog_and_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = _selected_uninstall_observations(tmp_path, monkeypatch)

    assert observed == (0, 0, {INSTALL_SCOPE_USER}, True, True, True), (
        "selected project uninstall should preserve the other scope and staged package"
    )


def test_marketplace_uninstall_integration_removes_registered_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host, project, _ = _host(tmp_path, monkeypatch)
    request = NativeRequest(False, USER_AND_PROJECT[:1], project)
    install_status = install_marketplace_host(host, request, BINARY)
    uninstall_status = uninstall_marketplace_host(host, request)
    remaining_scopes = _registration_scopes(host, project)
    marketplace_remains = FAKE_MARKETPLACE_NAME in host.marketplace_sources(project)

    assert (
        install_status,
        uninstall_status,
        remaining_scopes,
        marketplace_remains,
    ) == (0, 0, set(), True), (
        "native uninstall should remove its scope without deleting the shared catalog"
    )


@settings(max_examples=PROPERTY_EXAMPLES, deadline=None)
@given(case=INSTALL_CASES)
def test_install_marketplace_host_property_registers_only_requested_scope(
    tmp_path_factory: pytest.TempPathFactory,
    case: tuple[str, str],
) -> None:
    scope, binary = case

    assert _install_matches_requested_scope(tmp_path_factory, scope, binary), (
        "marketplace install should create one requested-scope registration at the rendered version"
    )
