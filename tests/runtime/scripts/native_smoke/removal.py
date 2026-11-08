from __future__ import annotations

from .native import (
    CLAUDE_ID,
    OMP_ID,
    SCOPES,
    SlopgateAction,
    claude_plugins,
    claude_registration,
    claude_marketplace_source,
    native_inventory_snapshot,
    omp_entries,
    omp_marketplace_source,
    omp_registration,
    package_root,
    pi_package_source,
    run_slopgate,
    stage_root,
)
from .project import (
    assert_claude_legacy_hooks_removed,
    assert_legacy_paths_removed,
)
from .runtime import assert_omp_inventory, assert_pi_discovery
from .sandbox import Sandbox, SmokeFailure
from .seed import assert_unrelated_entries_preserved
from .snapshot import tree_hash

HOSTS = ("omp", "pi", "claude")


def _show_result(label: str, stdout: str) -> None:
    print(f"--- {label} ---")
    print(stdout.rstrip() if stdout.strip() else "(no output)")


def assert_dry_runs_are_read_only(sandbox: Sandbox) -> None:
    inventories_before = native_inventory_snapshot(sandbox)
    tree_before = tree_hash(sandbox.root)
    for action in ("install", "uninstall"):
        for host in HOSTS:
            result = run_slopgate(
                sandbox,
                SlopgateAction(action, host, "both", dry_run=True),
            )
            _show_result(f"dry-run {action} {host}", result.stdout)
    inventories_after = native_inventory_snapshot(sandbox)
    tree_after = tree_hash(sandbox.root)
    if inventories_after != inventories_before:
        raise SmokeFailure("Native inventory changed during dry-run install/uninstall")
    if tree_after != tree_before:
        raise SmokeFailure("Sandbox tree changed during dry-run install/uninstall")
    print(f"Dry-run read-only tree hash: {tree_before}")


def _assert_user_removed_project_retained(sandbox: Sandbox, host: str) -> None:
    if host == "omp":
        if (
            omp_registration(sandbox, "user") is not None
            or omp_registration(sandbox, "project") is None
        ):
            raise SmokeFailure(
                "OMP user uninstall did not preserve the project registration"
            )
        assert_omp_inventory(sandbox, "project")
    elif host == "pi":
        if (
            pi_package_source(sandbox, "user") is not None
            or pi_package_source(sandbox, "project") is None
        ):
            raise SmokeFailure(
                "Pi user uninstall did not preserve the project package source"
            )
        assert_pi_discovery(sandbox, True)
    else:
        if (
            claude_registration(sandbox, "user") is not None
            or claude_registration(sandbox, "project") is None
        ):
            raise SmokeFailure(
                "Claude user uninstall did not preserve the project plugin"
            )


def _assert_plugin_removed(sandbox: Sandbox, host: str) -> None:
    if host == "omp" and omp_entries(sandbox, OMP_ID):
        raise SmokeFailure(
            "Final OMP Slopgate registration remains in native inventory"
        )
    if host == "pi":
        if any(pi_package_source(sandbox, scope) is not None for scope in SCOPES):
            raise SmokeFailure(
                "Final Pi Slopgate package source remains in native settings"
            )
        assert_pi_discovery(sandbox, False)
    if host == "claude" and claude_plugins(sandbox, CLAUDE_ID):
        raise SmokeFailure("Final Claude Slopgate plugin remains in native inventory")
    if host == "omp":
        assert_omp_inventory(sandbox, None)


def _assert_owned_staging_retained(sandbox: Sandbox) -> None:
    for host in HOSTS:
        if not stage_root(sandbox, host).is_dir():
            raise SmokeFailure(f"Uninstall removed retained Slopgate {host} staging")
    if omp_marketplace_source(sandbox) != package_root(sandbox, "omp").resolve():
        raise SmokeFailure("OMP native marketplace was removed during uninstall")
    if claude_marketplace_source(sandbox) != package_root(sandbox, "claude").resolve():
        raise SmokeFailure("Claude native marketplace was removed during uninstall")
    if not (package_root(sandbox, "pi") / "index.ts").is_file():
        raise SmokeFailure("Pi native package bytes were removed during uninstall")


def assert_selected_uninstall(sandbox: Sandbox) -> None:
    for host in HOSTS:
        result = run_slopgate(sandbox, SlopgateAction("uninstall", host, "user"))
        _show_result(f"selected user-scope uninstall {host}", result.stdout)
        _assert_user_removed_project_retained(sandbox, host)
    assert_unrelated_entries_preserved(sandbox)
    for host in HOSTS:
        result = run_slopgate(sandbox, SlopgateAction("uninstall", host, "project"))
        _show_result(f"final project-scope uninstall {host}", result.stdout)
        _assert_plugin_removed(sandbox, host)
        assert_unrelated_entries_preserved(sandbox)
    for host in ("omp", "pi"):
        assert_legacy_paths_removed(sandbox, host)
    assert_claude_legacy_hooks_removed(sandbox)
    _assert_owned_staging_retained(sandbox)
