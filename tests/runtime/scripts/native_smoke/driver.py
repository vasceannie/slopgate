from __future__ import annotations

import atexit
import json
import shutil
from pathlib import Path
from typing import cast

from .installation import (
    assert_both_scope_precedence,
    assert_explicit_refresh,
    assert_idempotent_reinstall,
    assert_initial_cutover,
    assert_single_scope_disable_and_reenable,
    execute_registered_runtime_contracts,
    install_both_scopes,
    seed_native_and_legacy_state,
)
from .native import run_host
from .project import prepare_project
from .removal import assert_dry_runs_are_read_only, assert_selected_uninstall
from .sandbox import Sandbox, SmokeFailure, create_sandbox

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
# Harnesses release too often to pin: the smoke reports what it ran against and
# only fails on real behavior, never on a version mismatch.
SMOKED_HOSTS = ("omp", "pi", "claude")
RUNNER_PACKAGE_FILES = {
    "omp": "tests/runtime/omp/node_modules/@oh-my-pi/pi-coding-agent/package.json",
    "pi": "tests/runtime/pi/node_modules/@earendil-works/pi-coding-agent/package.json",
}


def _report_host_versions(sandbox: Sandbox) -> None:
    for host in SMOKED_HOSTS:
        result = run_host(sandbox, host, ["--version"])
        version = (result.stdout + result.stderr).strip()
        print(f"Installed host under smoke: {host} {version}")


def _report_runner_versions(sandbox: Sandbox) -> None:
    for host, relative in RUNNER_PACKAGE_FILES.items():
        path = sandbox.repo / relative
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except OSError as error:
            raise SmokeFailure(
                f"The {host} runtime runner is not installed: {path}"
            ) from error
        if not isinstance(parsed, dict):
            raise SmokeFailure(f"The {host} runner metadata is malformed: {path}")
        version = cast(dict[str, object], parsed).get("version")
        print(f"Runtime runner under smoke: {host} {version}")


def _register_cleanup(sandbox: Sandbox) -> None:
    atexit.register(shutil.rmtree, sandbox.root, ignore_errors=True)
    atexit.register(
        print,
        "MANUAL ACCEPTANCE REQUIRED: Claude /hooks inventory in a separate "
        "authenticated Claude TUI session: open the registered plugin's project, "
        "run /hooks, confirm the Slopgate plugin origin, and exercise a protected "
        "mutation against the rule engine. This driver does not authenticate or "
        "claim Claude runtime activation.",
    )


def _print_receipt(sandbox: Sandbox) -> None:
    print(f"Disposable sandbox: {sandbox.root}")
    print(f"Sandbox HOME: {sandbox.home}")
    print(f"Enrolled project: {sandbox.project}")
    print(f"Checkout Slopgate executable: {sandbox.slopgate_binary}")


def run() -> int:
    sandbox = create_sandbox(REPOSITORY_ROOT)
    _register_cleanup(sandbox)
    if sandbox.omp_agent.resolve() == sandbox.pi_agent.resolve():
        raise SmokeFailure(
            "OMP and Pi must use separate sandbox PI_CODING_AGENT_DIR roots"
        )
    prepare_project(sandbox)
    _report_host_versions(sandbox)
    _report_runner_versions(sandbox)
    _print_receipt(sandbox)
    seed_native_and_legacy_state(sandbox)
    install_both_scopes(sandbox)
    registrations = assert_initial_cutover(sandbox)
    for receipt in registrations:
        print(f"Native registration verified: {receipt}")
    gaps = execute_registered_runtime_contracts(sandbox)
    assert_both_scope_precedence(sandbox)
    print("Both-scope native precedence and Pi package filters verified")
    assert_idempotent_reinstall(sandbox)
    print("Same-input native reinstall is idempotent")
    assert_single_scope_disable_and_reenable(sandbox)
    print("Single-scope disable/re-enable, native inventory, and Pi discovery verified")
    assert_explicit_refresh(sandbox)
    print("Explicit refresh changed invocations while preserving disabled/filter state")
    assert_dry_runs_are_read_only(sandbox)
    assert_selected_uninstall(sandbox)
    print(
        "Selected-scope removal, native inventory, Pi discovery, and unrelated "
        "registrations verified"
    )
    if gaps:
        print("KNOWN GAP: loaded package dir unprotected")
        for gap in gaps:
            print(f"- {gap}")
        return 1
    print("Native OMP/Pi/Claude manager smoke: PASS")
    return 0
