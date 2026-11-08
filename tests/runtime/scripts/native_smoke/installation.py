from __future__ import annotations

import shutil
from pathlib import Path

from .control import (
    capture_pi_entry,
    native_enabled,
    set_native_enabled,
    set_pi_extensions,
)
from .native import (
    SCOPES,
    SlopgateAction,
    assert_initial_inventory_clear,
    claude_registration,
    native_inventory_snapshot,
    omp_registration,
    pi_package_source,
    run_slopgate,
)
from .project import (
    assert_claude_legacy_hooks_removed,
    assert_legacy_paths_removed,
    seed_legacy_installations,
)
from .registration import assert_registrations
from .runtime import (
    RuntimeEvidence,
    assert_omp_inventory,
    assert_pi_discovery,
    assert_runtime_contract,
    run_omp_extension,
    run_pi_extension,
)
from .sandbox import Sandbox, SmokeFailure
from .snapshot import staged_payload_hash, staged_payload_uses_binary, staged_version
from .seed import assert_unrelated_entries_preserved, seed_unrelated_native_entries

HOSTS = ("omp", "pi", "claude")


def _show_result(label: str, stdout: str) -> None:
    print(f"--- {label} ---")
    print(stdout.rstrip() if stdout.strip() else "(no output)")


def seed_native_and_legacy_state(sandbox: Sandbox) -> None:
    assert_initial_inventory_clear(sandbox)
    seed_unrelated_native_entries(sandbox)
    seed_legacy_installations(sandbox)


def install_both_scopes(sandbox: Sandbox) -> None:
    for host in HOSTS:
        result = run_slopgate(sandbox, SlopgateAction("install", host, "both"))
        _show_result(f"slopgate install {host} --install-scope both", result.stdout)


def assert_initial_cutover(sandbox: Sandbox) -> list[str]:
    receipts = assert_registrations(sandbox)
    for host in ("omp", "pi"):
        assert_legacy_paths_removed(sandbox, host)
    assert_claude_legacy_hooks_removed(sandbox)
    assert_unrelated_entries_preserved(sandbox)
    return receipts


def execute_registered_runtime_contracts(sandbox: Sandbox) -> list[str]:
    omp_index = assert_omp_inventory(sandbox, "project")
    pi_index = assert_pi_discovery(sandbox, True)
    if omp_index is None or pi_index is None:
        raise SmokeFailure(
            "Registered runtime discovery omitted an installed extension"
        )
    evidence: list[RuntimeEvidence] = [
        run_omp_extension(sandbox, omp_index),
        run_pi_extension(sandbox, pi_index),
    ]
    gaps: list[str] = []
    for item in evidence:
        gaps.extend(assert_runtime_contract(item))
        print(f"{item.host.upper()} ExtensionRunner contract: registered source loaded")
    return gaps


def assert_both_scope_precedence(sandbox: Sandbox) -> None:
    assert_omp_inventory(sandbox, "project")
    project_entry = capture_pi_entry(sandbox, "project")
    set_pi_extensions(sandbox, "project", project_entry, [])
    assert_pi_discovery(sandbox, False)
    set_pi_extensions(sandbox, "project", project_entry, None)
    assert_pi_discovery(sandbox, True)
    for scope in SCOPES:
        if omp_registration(sandbox, scope) is None:
            raise SmokeFailure(
                f"OMP {scope} registration disappeared during precedence check"
            )
        if claude_registration(sandbox, scope) is None:
            raise SmokeFailure(
                f"Claude {scope} registration disappeared during precedence check"
            )


def assert_idempotent_reinstall(sandbox: Sandbox) -> None:
    stage_hashes = {host: staged_payload_hash(sandbox, host) for host in HOSTS}
    inventory_before = native_inventory_snapshot(sandbox)
    for host in HOSTS:
        result = run_slopgate(sandbox, SlopgateAction("install", host, "both"))
        _show_result(f"idempotent reinstall {host}", result.stdout)
    if native_inventory_snapshot(sandbox) != inventory_before:
        raise SmokeFailure(
            "Idempotent reinstall changed native inventories or settings"
        )
    for host in HOSTS:
        if staged_payload_hash(sandbox, host) != stage_hashes[host]:
            raise SmokeFailure(
                f"Idempotent reinstall rewrote {host} staged payload bytes"
            )
    assert_registrations(sandbox)


def _assert_project_only(sandbox: Sandbox, host: str) -> None:
    if host == "omp":
        user, project = (
            omp_registration(sandbox, "user"),
            omp_registration(sandbox, "project"),
        )
    elif host == "claude":
        user, project = (
            claude_registration(sandbox, "user"),
            claude_registration(sandbox, "project"),
        )
    else:
        user, project = (
            pi_package_source(sandbox, "user"),
            pi_package_source(sandbox, "project"),
        )
    if user is not None or project is None:
        raise SmokeFailure(
            f"{host} did not retain exactly its project-scope registration"
        )


def _disable_and_reenable_project(sandbox: Sandbox, host: str) -> None:
    if host == "pi":
        original = capture_pi_entry(sandbox, "project")
        set_pi_extensions(sandbox, "project", original, [])
        package = pi_package_source(sandbox, "project")
        if package is None or package.get("extensions") != []:
            raise SmokeFailure("Pi project resource filter did not disable the package")
        assert_pi_discovery(sandbox, False)
        set_pi_extensions(sandbox, "project", original, None)
        assert_pi_discovery(sandbox, True)
        return
    set_native_enabled(sandbox, host, "project", False)
    if native_enabled(sandbox, host, "project"):
        raise SmokeFailure(
            f"{host} native manager did not record the disabled project state"
        )
    if host == "omp":
        assert_omp_inventory(sandbox, None)
    set_native_enabled(sandbox, host, "project", True)
    if not native_enabled(sandbox, host, "project"):
        raise SmokeFailure(
            f"{host} native manager did not restore the enabled project state"
        )
    if host == "omp":
        assert_omp_inventory(sandbox, "project")


def assert_single_scope_disable_and_reenable(sandbox: Sandbox) -> None:
    for host in HOSTS:
        result = run_slopgate(sandbox, SlopgateAction("uninstall", host, "user"))
        _show_result(f"prepare single-scope {host}", result.stdout)
        _assert_project_only(sandbox, host)
        if host == "omp":
            assert_omp_inventory(sandbox, "project")
        if host == "pi":
            assert_pi_discovery(sandbox, True)
        _disable_and_reenable_project(sandbox, host)
        result = run_slopgate(sandbox, SlopgateAction("install", host, "user"))
        _show_result(f"restore user-scope {host}", result.stdout)
    assert_registrations(sandbox)
    assert_unrelated_entries_preserved(sandbox)


def _alternate_binary(sandbox: Sandbox) -> Path:
    target = sandbox.alternate_bin / sandbox.slopgate_binary.name
    shutil.copy2(sandbox.slopgate_binary, target)
    if not target.is_file():
        raise SmokeFailure(f"Could not create alternate Slopgate executable: {target}")
    return target.resolve()


def _prepare_refresh_state(
    sandbox: Sandbox,
) -> tuple[dict[str, str], dict[str, object], dict[str, dict[str, object] | None]]:
    versions = {host: staged_version(sandbox, host) for host in HOSTS}
    pi_original = {scope: capture_pi_entry(sandbox, scope) for scope in SCOPES}
    set_native_enabled(sandbox, "omp", "user", False)
    set_native_enabled(sandbox, "claude", "user", False)
    set_pi_extensions(sandbox, "user", pi_original["user"], [])
    set_pi_extensions(sandbox, "project", pi_original["project"], ["index.ts"])
    filters = {scope: pi_package_source(sandbox, scope) for scope in SCOPES}
    return versions, pi_original, filters


def _refresh_host(
    sandbox: Sandbox, host: str, alternate: Path, previous_version: str
) -> None:
    result = run_slopgate(
        sandbox,
        SlopgateAction("install", host, "both", alternate_binary=True),
    )
    _show_result(f"explicit refresh {host} with alternate binary", result.stdout)
    if not staged_payload_uses_binary(sandbox, host, alternate):
        raise SmokeFailure(
            f"Explicit {host} refresh did not embed the alternate invocation"
        )
    if staged_version(sandbox, host) == previous_version:
        raise SmokeFailure(
            f"Explicit {host} refresh did not create a changed content version"
        )


def _assert_refresh_state(
    sandbox: Sandbox, filters: dict[str, dict[str, object] | None]
) -> None:
    if native_enabled(sandbox, "omp", "user") or native_enabled(
        sandbox, "claude", "user"
    ):
        raise SmokeFailure("Explicit refresh changed a recorded disabled native state")
    for scope in SCOPES:
        if pi_package_source(sandbox, scope) != filters[scope]:
            raise SmokeFailure(f"Explicit refresh changed Pi {scope} resource filters")
    assert_omp_inventory(sandbox, "project")
    assert_pi_discovery(sandbox, True)


def _restore_refresh_state(sandbox: Sandbox, pi_original: dict[str, object]) -> None:
    set_native_enabled(sandbox, "omp", "user", True)
    set_native_enabled(sandbox, "claude", "user", True)
    for scope in SCOPES:
        set_pi_extensions(sandbox, scope, pi_original[scope], None)


def assert_explicit_refresh(sandbox: Sandbox) -> None:
    previous_versions, pi_original, filters = _prepare_refresh_state(sandbox)
    alternate = _alternate_binary(sandbox)
    for host in HOSTS:
        _refresh_host(sandbox, host, alternate, previous_versions[host])
    _assert_refresh_state(sandbox, filters)
    for host in HOSTS:
        print(f"{host} refreshed staged version: {staged_version(sandbox, host)}")
    _restore_refresh_state(sandbox, pi_original)
    assert_registrations(sandbox)
