from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

import slopgate.installer.native.entry
import slopgate.installer.native.hook_install
from slopgate._types import object_dict, object_list
from slopgate.adapters.omp import OmpAdapter
from slopgate.constants import INSTALL_SCOPE_USER, POST_TOOL_USE
from slopgate.installer._claude import install_claude
from slopgate.installer._omp import install_omp
from slopgate.installer._pi import install_pi
from slopgate.installer.native.commands import (
    native_executable_available,
    run_native_command,
)
from slopgate.installer.native.entry import run_native_install
from slopgate.installer.native.hook_install import prepare_native_hooks_install
from slopgate.installer.native.marketplace.state import (
    Preflight,
    marketplace_command,
    scope_commands,
)
from slopgate.installer.native.model import NativeRequest
from slopgate.installer.native.omp import OMP_PLUGIN_ID, OmpMarketplaceHost
from slopgate.installer.native.packages import PackagePlan
from slopgate.installer.native.pi.commands import (
    pi_environment,
    pi_scope_command,
    run_pi_command,
)
from slopgate.models import RuleFinding, Severity
from tests.native.claude_fake import PLUGIN_ID
from tests.native.hosts import FakeHosts, install_fake_hosts
from tests.native.omp_fake import read_fake_state
from tests.native.pi_support import PiHarness, make_harness
from tests.omp_installer_support import TEST_BINARY, prepare_omp_sandbox


def _pi_commands(harness: PiHarness) -> list[list[str]]:
    return [cast(list[str], call["argv"]) for call in harness.fake.calls()]


def _rollback_inventory(state_path: Path) -> tuple[int, int]:
    state = read_fake_state(state_path)
    return (
        len(object_list(state.get("registrations"))),
        len(object_dict(state.get("marketplaces"))),
    )


def _claude_staged_registration(
    hosts: FakeHosts,
) -> tuple[object, bool, object, bool]:
    native_state = cast(
        dict[str, object],
        json.loads(hosts.claude_state_path.read_text(encoding="utf-8")),
    )
    registration = object_dict(object_list(native_state.get("plugins"))[0])
    marketplace_root = hosts.staging_root / "claude" / "marketplace"
    catalog_path = marketplace_root / ".claude-plugin" / "marketplace.json"
    catalog = cast(
        dict[str, object], json.loads(catalog_path.read_text(encoding="utf-8"))
    )
    entry = object_dict(object_list(catalog.get("plugins"))[0])
    plugin_root = marketplace_root / cast(str, entry["source"]).removeprefix("./")
    manifest_path = plugin_root / ".claude-plugin" / "plugin.json"
    manifest = cast(
        dict[str, object], json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    return (
        registration.get("id"),
        entry.get("version") == manifest.get("version"),
        manifest.get("name"),
        (plugin_root / "hooks" / "hooks.json").is_file(),
    )


def _failed_omp_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, PackagePlan, Path]:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path, TEST_BINARY)
    plan = OmpMarketplaceHost().build_plan(TEST_BINARY)
    monkeypatch.setenv("FAKE_OMP_FAIL_ON", "plugin install")
    monkeypatch.setenv("FAKE_OMP_FAIL_AFTER_MUTATION", "1")
    status = install_omp(scope=INSTALL_SCOPE_USER, project_root=sandbox.project_root)
    return status, plan, sandbox.state_path


def _omp_inventory(stdout: str) -> tuple[str, str, str]:
    inventory = cast(dict[str, object], json.loads(stdout))
    plugins = object_list(inventory.get("marketplace"))
    plugin = object_dict(plugins[0])
    entry = object_dict(object_list(plugin.get("entries"))[0])
    return (
        cast(str, plugin.get("id")),
        cast(str, plugin.get("scope")),
        cast(str, entry.get("version")),
    )


def test_omp_installer_integration_registers_native_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path, TEST_BINARY)
    available = native_executable_available("omp")
    status = install_omp(scope=INSTALL_SCOPE_USER, project_root=sandbox.project_root)
    completed = run_native_command(
        ["omp", "plugin", "list", "--json"],
        cwd=sandbox.project_root,
        platform="omp",
    )
    version = OmpMarketplaceHost().build_plan(TEST_BINARY).version
    observed = (
        available,
        status,
        completed.returncode,
        _omp_inventory(completed.stdout),
    )

    assert observed == (
        True,
        0,
        0,
        (OMP_PLUGIN_ID, INSTALL_SCOPE_USER, version),
    ), "public OMP install should register the exact native identity and version"


def test_omp_installer_integration_uses_native_scope_planning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = prepare_omp_sandbox(monkeypatch, tmp_path, TEST_BINARY)
    host = OmpMarketplaceHost()
    plan = host.build_plan(TEST_BINARY)
    state = Preflight(False, False, {})
    marketplace = marketplace_command(host, plan, state)
    scoped = scope_commands(host, INSTALL_SCOPE_USER, (None, plan.version))
    status = install_omp(scope=INSTALL_SCOPE_USER, project_root=sandbox.project_root)

    assert (
        marketplace,
        scoped,
        status,
    ) == (
        ["omp", "plugin", "marketplace", "add", str(plan.entry_root)],
        [["omp", "plugin", "install", "--scope", "user", OMP_PLUGIN_ID]],
        0,
    ), "native marketplace and scope commands should drive public OMP installation"


def test_omp_install_integration_rolls_back_failed_native_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status, plan, state_path = _failed_omp_install(tmp_path, monkeypatch)
    registration_count, marketplace_count = _rollback_inventory(state_path)

    assert (
        status,
        registration_count,
        marketplace_count,
        plan.entry_root.exists(),
    ) == (1, 0, 0, False), (
        "failed native registration should remove inventory and owned staging"
    )


def test_pi_installer_integration_routes_native_scope_and_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    request = NativeRequest(False, (INSTALL_SCOPE_USER,), harness.project)
    expected = pi_scope_command("install", harness.package_root, INSTALL_SCOPE_USER)[1:]
    status = install_pi(scope=INSTALL_SCOPE_USER, project_root=harness.project)
    listing = run_pi_command(["pi", "list"], request)
    environment = pi_environment()
    actual_commands = _pi_commands(harness)

    assert (
        status,
        expected in actual_commands,
        str(harness.agent_dir) == environment["PI_CODING_AGENT_DIR"],
        str(harness.package_root) in listing,
    ) == (0, True, True, True), (
        "public Pi install should register its package in the active native scope"
    )


def test_claude_installer_integration_stages_registered_plugin_and_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hosts = install_fake_hosts(monkeypatch, tmp_path)
    status = install_claude(scope=INSTALL_SCOPE_USER, project_root=hosts.project)
    registration_id, versions_match, plugin_name, hooks_staged = (
        _claude_staged_registration(hosts)
    )

    assert (
        status,
        registration_id,
        versions_match,
        plugin_name,
        hooks_staged,
    ) == (0, PLUGIN_ID, True, "slopgate-enforcement", True), (
        "public Claude install should register the staged plugin and hook payload"
    )


def test_omp_post_tool_integration_renders_block_reason() -> None:
    finding = RuleFinding(
        rule_id="OMP-POST",
        title="OMP post tool",
        severity=Severity.HIGH,
        decision="block",
        message="inspect result",
        additional_context="inspect the result",
    )
    rendered = OmpAdapter().render_output(
        POST_TOOL_USE,
        [finding],
        context="inspect the result",
        updated_input={},
        decision="block",
    )

    assert rendered == {
        "context": "inspect the result",
        "reason": "[OMP-POST | HIGH] inspect result",
        "tool_result_patch": {
            "details": {
                "slopgate": {
                    "decision": "block",
                    "context": "inspect the result",
                    "reason": "[OMP-POST | HIGH] inspect result",
                }
            }
        },
    }, "post-tool integration should preserve the denial reason in OMP guidance"


def test_shared_native_install_entry_dispatches_valid_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setattr(
        slopgate.installer.native.entry,
        "find_binary",
        lambda: "native-entry-test-binary",
    )
    calls: list[tuple[NativeRequest, str]] = []

    def install(request: NativeRequest, binary: str) -> int:
        calls.append((request, binary))
        return 0

    status = run_native_install(INSTALL_SCOPE_USER, root, True, install)
    observed = (
        status,
        calls[0][0].dry_run,
        calls[0][0].scopes,
        calls[0][0].root,
        calls[0][1],
    )

    assert observed == (
        0,
        True,
        (INSTALL_SCOPE_USER,),
        root.resolve(),
        "native-entry-test-binary",
    ), "shared native dispatch should preserve validated request fields"


def test_shared_native_install_entry_refuses_invalid_scope_before_dispatch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    calls: list[tuple[NativeRequest, str]] = []

    def install(request: NativeRequest, binary: str) -> int:
        calls.append((request, binary))
        return 0

    status = run_native_install("invalid-scope", root, False, install)

    assert (status, calls) == (1, []), (
        "invalid native scope should return failure without resolving or dispatching an install"
    )


def test_shared_native_hook_preparation_resolves_scope_and_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        slopgate.installer.native.hook_install,
        "find_binary",
        lambda: "native-hook-test-binary",
    )
    observed = prepare_native_hooks_install(INSTALL_SCOPE_USER)

    assert observed == (INSTALL_SCOPE_USER, "native-hook-test-binary"), (
        "native hook setup should resolve one selected scope and the Slopgate binary"
    )
