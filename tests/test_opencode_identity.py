from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given, strategies

from slopgate._types import ObjectDict
from slopgate.installer import _opencode, opencode_identity


@dataclass(frozen=True, slots=True)
class IdentityVersions:
    declared: str
    locked: str
    installed: str


def _write_identity_metadata(config_dir: Path, versions: IdentityVersions) -> None:
    package_dir = config_dir / "node_modules" / "@opencode" / "plugin"
    package_dir.mkdir(parents=True)
    (config_dir / "package.json").write_text(
        json.dumps({"dependencies": {"@opencode/plugin": versions.declared}}),
        encoding="utf-8",
    )
    (config_dir / "bun.lock").write_text(
        json.dumps(
            {
                "workspaces": {
                    "": {"dependencies": {"@opencode/plugin": versions.locked}}
                }
            }
        ),
        encoding="utf-8",
    )
    (package_dir / "package.json").write_text(
        json.dumps({"version": versions.installed}), encoding="utf-8"
    )


def _identity_for_local_versions(versions: tuple[str, str, str]) -> ObjectDict:
    with TemporaryDirectory() as temporary_dir, pytest.MonkeyPatch.context() as patch:
        temporary_path = Path(temporary_dir)
        config_dir = temporary_path / "opencode"
        _write_identity_metadata(config_dir, IdentityVersions(*versions))
        patch.setattr(opencode_identity, "opencode_runtime_version", lambda: "2.2.5")
        return _opencode.collect_opencode_install_identity(
            str(temporary_path / "slopgate"), config_dir=config_dir
        )


@given(
    strategies.tuples(
        strategies.text(min_size=1, max_size=32),
        strategies.text(min_size=1, max_size=32),
        strategies.text(min_size=1, max_size=32),
    )
)
def test_opencode_identity_status_ignores_local_dependency_versions(
    versions: tuple[str, str, str],
) -> None:
    identity = _identity_for_local_versions(versions)
    assert identity["status"] == "compatible", (
        "host-derived compatibility must ignore arbitrary local package metadata"
    )


def test_opencode_identity_rejects_v1_host_while_preserving_local_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "opencode"
    _write_identity_metadata(
        config_dir,
        IdentityVersions(declared="1.18.5", locked="1.2.27", installed="1.18.5"),
    )
    monkeypatch.setattr(
        opencode_identity, "opencode_runtime_version", lambda: "1.18.19"
    )

    identity = _opencode.collect_opencode_install_identity(
        str(tmp_path / "slopgate"), config_dir=config_dir
    )

    assert identity["status"] == "stale", "v1 hosts cannot load the v2 plugin"
    assert identity["opencode_version"] == "1.18.19", "CLI version should be recorded"
    assert identity["plugin_declared_version"] == "1.18.5", "declared version lost"
    assert identity["plugin_lock_version"] == "1.2.27", "lock version lost"
    assert identity["plugin_installed_version"] == "1.18.5", "installed version lost"
    remediation = str(identity["remediation"]).lower()
    assert "upgrade" in remediation, "stale diagnostics should recommend an upgrade"
    assert "restart" in remediation, "stale diagnostics should recommend restart"


def test_opencode_identity_reads_bun_generated_lockfile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "opencode"
    version = "2.2.5"
    _write_identity_metadata(
        config_dir,
        IdentityVersions(declared=version, locked=version, installed=version),
    )
    (config_dir / "bun.lock").write_text(
        """{
  "workspaces": {
    "": {
      "dependencies": {
        "@opencode/plugin": "2.2.5",
      },
    },
  },
}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(opencode_identity, "opencode_runtime_version", lambda: version)

    identity = _opencode.collect_opencode_install_identity(
        str(tmp_path / "slopgate"), config_dir=config_dir
    )

    assert identity["plugin_lock_version"] == version, (
        "Bun's generated JSONC lockfile should expose the pinned plugin version"
    )
    assert identity["status"] == "compatible", (
        "host runtime and supported API target should determine compatibility"
    )
    assert identity["plugin_package"] == "@opencode/plugin"
    assert identity["plugin_api_target"] == "2.2.5"
    assert identity["dependency_resolution"] == "opencode-host"


def test_opencode_identity_is_compatible_for_equivalent_version_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "opencode"
    _write_identity_metadata(
        config_dir,
        IdentityVersions(declared="^2.2.5", locked="2.2.5", installed="v2.2.5"),
    )
    monkeypatch.setattr(
        opencode_identity,
        "opencode_runtime_version",
        lambda: "opencode 2.2.5",
    )

    identity = _opencode.collect_opencode_install_identity(
        str(tmp_path / "slopgate"), config_dir=config_dir
    )

    assert identity["status"] == "compatible", (
        "verified host runtime and supported API target should be compatible"
    )
    assert identity["plugin_declared_version"] == "^2.2.5", (
        "declared specifier should remain the raw observed value"
    )


def test_opencode_identity_ignores_local_dependency_skew_for_host_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "opencode"
    _write_identity_metadata(
        config_dir,
        IdentityVersions(declared="1.18.5", locked="1.2.27", installed="1.18.5"),
    )
    monkeypatch.setattr(
        opencode_identity, "opencode_runtime_version", lambda: "opencode 2.2.5"
    )

    identity = _opencode.collect_opencode_install_identity(
        str(tmp_path / "slopgate"), config_dir=config_dir
    )

    assert identity["status"] == "compatible", (
        "host-provided v2 dependencies must not be stale due to local remnants"
    )
    assert identity["plugin_declared_version"] == "1.18.5"
    assert identity["plugin_lock_version"] == "1.2.27"
    assert identity["plugin_installed_version"] == "1.18.5"


def test_opencode_identity_accepts_host_runtime_without_local_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "opencode"
    config_dir.mkdir()
    monkeypatch.setattr(
        opencode_identity, "opencode_runtime_version", lambda: "opencode 2.2.5"
    )

    identity = _opencode.collect_opencode_install_identity(
        str(tmp_path / "slopgate"), config_dir=config_dir
    )

    assert identity["status"] == "compatible", (
        "host-provided dependencies do not require local package metadata"
    )
    assert identity["plugin_declared_version"] == ""
    assert identity["plugin_lock_version"] == ""
    assert identity["plugin_installed_version"] == ""


def test_opencode_identity_is_unknown_for_unverified_v2_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "opencode"
    config_dir.mkdir()
    monkeypatch.setattr(opencode_identity, "opencode_runtime_version", lambda: "2.3.0")

    identity = _opencode.collect_opencode_install_identity(
        str(tmp_path / "slopgate"), config_dir=config_dir
    )

    assert identity["status"] == "unknown", (
        "unverified future OpenCode releases must not overclaim API compatibility"
    )
    assert "not verified" in str(identity["remediation"])


def test_opencode_identity_is_unknown_when_no_versions_are_observed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "opencode"
    config_dir.mkdir()
    monkeypatch.setattr(opencode_identity, "opencode_runtime_version", lambda: "")

    identity = _opencode.collect_opencode_install_identity(
        str(tmp_path / "slopgate"),
        config_dir=config_dir,
        probe_runtime=False,
    )

    assert identity["status"] == "unknown", (
        "missing runtime, declared, lock, and installed versions are unknown, not stale"
    )
    assert "could not be observed" in str(identity["remediation"]), (
        "unknown identity should explain that no versions were observed"
    )
