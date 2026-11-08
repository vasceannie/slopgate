from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, TypeAlias, cast

import pytest

import slopgate.installer
import slopgate.installer._shared
import slopgate.installer._suite
import slopgate.installer.native.entry
from slopgate._types import object_dict, object_list, string_value
from tests.native import read_fake_state
from tests.native.hosts import FakeHosts

pytestmark = pytest.mark.usefixtures("native_hosts")

_UPDATE_SOURCE = "git+https://example.invalid/vf.git@main"

SubprocessResult: TypeAlias = (
    subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str]
)


def _file_bytes(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def _native_snapshot(hosts: FakeHosts) -> tuple[object, ...]:
    return (
        hosts.staging_digest(),
        _file_bytes(hosts.omp_state_path),
        _file_bytes(hosts.claude_state_path),
        _file_bytes(hosts.pi.state_path),
        _file_bytes(hosts.pi.agent_dir / "settings.json"),
        _file_bytes(hosts.home / ".claude" / "settings.json"),
    )


def _pi_mutation_records(hosts: FakeHosts) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for record in hosts.pi_calls():
        argv = record.get("argv")
        if (
            isinstance(argv, list)
            and argv
            and argv[0]
            in {
                "install",
                "remove",
                "uninstall",
            }
        ):
            records.append(record)
    return records


def _install_native_hosts(hosts: FakeHosts, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(hosts.project)
    for platform in ("claude", "omp", "pi"):
        assert slopgate.installer.install_platform(platform) == 0, (
            f"{platform} native installation should succeed"
        )


def _is_generated_package_update_argv(command: list[str], source: str) -> bool:
    uv_update = (
        bool(command)
        and Path(command[0]).stem == "uv"
        and command[1:] == ["tool", "install", "--force", source]
    )
    pip_update = command == [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        source,
    ]
    return uv_update or pip_update


def _record_package_update_command(
    monkeypatch: pytest.MonkeyPatch, source: str
) -> list[list[str]]:
    saved_run = subprocess.run
    observed: list[list[str]] = []
    runner = cast(Callable[..., SubprocessResult], saved_run)

    def record_run(*args: object, **kwargs: object) -> SubprocessResult:
        command = args[0] if args else kwargs.get("args")
        if isinstance(command, list):
            parts = cast(list[object], command)
            if all(isinstance(part, str) for part in parts):
                package_argv = cast(list[str], parts)
                if _is_generated_package_update_argv(package_argv, source):
                    observed.append(package_argv.copy())
                    return subprocess.CompletedProcess[bytes](package_argv, 0)
        return runner(*args, **kwargs)

    monkeypatch.setattr(slopgate.installer._suite.subprocess, "run", record_run)
    return observed


@dataclass(frozen=True, slots=True)
class _PackageUpdateObservation:
    status: int
    commands: tuple[list[str], ...]
    native_state_preserved: bool
    mutations_preserved: bool


def _package_update_observation(
    monkeypatch: pytest.MonkeyPatch, native_hosts: FakeHosts
) -> _PackageUpdateObservation:
    _install_native_hosts(native_hosts, monkeypatch)
    before = _native_snapshot(native_hosts)
    mutations = native_hosts.mutating_calls()
    observed_commands = _record_package_update_command(monkeypatch, _UPDATE_SOURCE)
    status = slopgate.installer.update_suite(
        slopgate.installer.SuiteUpdateOptions(source=_UPDATE_SOURCE)
    )
    return _PackageUpdateObservation(
        status,
        tuple(observed_commands),
        _native_snapshot(native_hosts) == before,
        native_hosts.mutating_calls() == mutations,
    )


def test_package_update_leaves_native_host_state_untouched(
    monkeypatch: pytest.MonkeyPatch, native_hosts: FakeHosts
) -> None:
    observed = _package_update_observation(monkeypatch, native_hosts)

    assert observed.status == 0, "package-only update should succeed"
    assert len(observed.commands) == 1 and _is_generated_package_update_argv(
        observed.commands[0], _UPDATE_SOURCE
    ), "package-only update must submit its generated uv or pip argv"
    assert observed.native_state_preserved, (
        "package-only update must preserve staged assets and native inventories"
    )
    assert observed.mutations_preserved, (
        "package-only update must not mutate native registrations"
    )


def _catalog_version(hosts: FakeHosts, platform: str) -> str:
    catalog_dir = ".claude-plugin" if platform == "claude" else ".omp-plugin"
    path = (
        hosts.staging_root / platform / "marketplace" / catalog_dir / "marketplace.json"
    )
    return str(json.loads(path.read_text(encoding="utf-8"))["plugins"][0]["version"])


class NativeRefreshSnapshot(NamedTuple):
    status: int
    old_staging_digest: str
    new_staging_digest: str
    old_pi_index: bytes
    new_pi_index: bytes
    old_catalog_versions: dict[str, str]
    new_catalog_versions: dict[str, str]
    registered_versions: dict[str, str]
    old_pi_mutations: list[dict[str, object]]
    new_pi_mutations: list[dict[str, object]]
    old_pi_settings: bytes | None
    new_pi_settings: bytes | None


def _refresh_native_hosts_snapshot(
    monkeypatch: pytest.MonkeyPatch, native_hosts: FakeHosts
) -> NativeRefreshSnapshot:
    _install_native_hosts(native_hosts, monkeypatch)
    old_staging_digest = native_hosts.staging_digest()
    old_catalog_versions = {
        host: _catalog_version(native_hosts, host) for host in ("claude", "omp")
    }
    pi_index = native_hosts.staging_root / "pi" / "package" / "index.ts"
    old_pi_index = pi_index.read_bytes()
    old_pi_settings = _file_bytes(native_hosts.pi.agent_dir / "settings.json")
    old_pi_mutations = _pi_mutation_records(native_hosts)
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "slopgate-refreshed"
    )
    monkeypatch.setattr(
        slopgate.installer.native.entry,
        "find_binary",
        lambda: "slopgate-refreshed",
    )
    update_commands = _record_package_update_command(monkeypatch, _UPDATE_SOURCE)
    status = slopgate.installer.update_suite(
        slopgate.installer.SuiteUpdateOptions(
            source=_UPDATE_SOURCE,
            refresh_hooks=True,
        )
    )

    assert len(update_commands) == 1 and _is_generated_package_update_argv(
        update_commands[0], _UPDATE_SOURCE
    ), "refresh update must submit its generated uv or pip package argv"
    claude_state = json.loads(native_hosts.claude_state_path.read_text())
    omp_state = read_fake_state(native_hosts.omp_state_path)
    claude_registration = object_dict(object_list(claude_state.get("plugins"))[0])
    omp_registration = object_dict(object_list(omp_state.get("registrations"))[0])
    claude_version = string_value(claude_registration.get("version"))
    omp_version = string_value(omp_registration.get("version"))
    if claude_version is None or omp_version is None:
        raise AssertionError("native registrations must record their catalog versions")
    registered_versions = {"claude": claude_version, "omp": omp_version}
    return NativeRefreshSnapshot(
        status,
        old_staging_digest,
        native_hosts.staging_digest(),
        old_pi_index,
        pi_index.read_bytes(),
        old_catalog_versions,
        {host: _catalog_version(native_hosts, host) for host in ("claude", "omp")},
        registered_versions,
        old_pi_mutations,
        _pi_mutation_records(native_hosts),
        old_pi_settings,
        _file_bytes(native_hosts.pi.agent_dir / "settings.json"),
    )


def test_refresh_hooks_updates_staged_payloads(
    monkeypatch: pytest.MonkeyPatch, native_hosts: FakeHosts
) -> None:
    snapshot = _refresh_native_hosts_snapshot(monkeypatch, native_hosts)

    assert (
        snapshot.status,
        snapshot.old_staging_digest != snapshot.new_staging_digest,
        snapshot.old_pi_index != snapshot.new_pi_index,
    ) == (0, True, True), (
        "explicit refresh should replace staged assets and Pi's rendered invocation"
    )


@pytest.mark.parametrize("host", ("claude", "omp"))
def test_refresh_hooks_publishes_new_marketplace_versions(
    host: str, monkeypatch: pytest.MonkeyPatch, native_hosts: FakeHosts
) -> None:
    snapshot = _refresh_native_hosts_snapshot(monkeypatch, native_hosts)

    assert snapshot.old_catalog_versions[host] != snapshot.new_catalog_versions[host], (
        f"{host} refresh should publish a new payload version"
    )


@pytest.mark.parametrize("host", ("claude", "omp"))
def test_refresh_hooks_keeps_native_versions_aligned_with_catalogs(
    host: str, monkeypatch: pytest.MonkeyPatch, native_hosts: FakeHosts
) -> None:
    snapshot = _refresh_native_hosts_snapshot(monkeypatch, native_hosts)

    assert snapshot.registered_versions[host] == snapshot.new_catalog_versions[host], (
        f"{host} registration should match its refreshed catalog version"
    )


def test_refresh_hooks_preserves_pi_source_and_filters(
    monkeypatch: pytest.MonkeyPatch, native_hosts: FakeHosts
) -> None:
    snapshot = _refresh_native_hosts_snapshot(monkeypatch, native_hosts)

    assert (
        snapshot.old_pi_mutations == snapshot.new_pi_mutations,
        snapshot.old_pi_settings == snapshot.new_pi_settings,
    ) == (True, True), "refresh should preserve Pi's source declaration and filters"
