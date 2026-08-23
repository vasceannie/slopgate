from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given, strategies

from slopgate.installer import _opencode, opencode_identity


@dataclass(frozen=True, slots=True)
class IdentityVersions:
    declared: str
    locked: str
    installed: str


def _write_identity_metadata(config_dir: Path, versions: IdentityVersions) -> None:
    package_dir = config_dir / "node_modules" / "@opencode-ai" / "plugin"
    package_dir.mkdir(parents=True)
    (config_dir / "package.json").write_text(
        json.dumps({"dependencies": {"@opencode-ai/plugin": versions.declared}}),
        encoding="utf-8",
    )
    (config_dir / "bun.lock").write_text(
        json.dumps(
            {
                "workspaces": {
                    "": {
                        "dependencies": {"@opencode-ai/plugin": versions.locked}
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (package_dir / "package.json").write_text(
        json.dumps({"version": versions.installed}), encoding="utf-8"
    )


def _matching_identity_status(version: str) -> str:
    with TemporaryDirectory() as temporary_dir, pytest.MonkeyPatch.context() as patch:
        temporary_path = Path(temporary_dir)
        config_dir = temporary_path / "opencode"
        versions = IdentityVersions(declared=version, locked=version, installed=version)
        _write_identity_metadata(config_dir, versions)
        patch.setattr(opencode_identity, "opencode_runtime_version", lambda: version)
        identity = _opencode.collect_opencode_install_identity(
            str(temporary_path / "slopgate"), config_dir=config_dir
        )
    return str(identity["status"])


def test_opencode_identity_reports_stale_declared_lock_and_installed_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "opencode"
    _write_identity_metadata(
        config_dir,
        IdentityVersions(declared="1.18.5", locked="1.2.27", installed="1.18.5"),
    )
    monkeypatch.setattr(opencode_identity, "opencode_runtime_version", lambda: "1.18.19")

    identity = _opencode.collect_opencode_install_identity(
        str(tmp_path / "slopgate"), config_dir=config_dir
    )

    assert identity["status"] == "stale", "lock skew must be diagnosed as stale"
    assert identity["opencode_version"] == "1.18.19", "CLI version should be recorded"
    assert identity["plugin_declared_version"] == "1.18.5", "declared version lost"
    assert identity["plugin_lock_version"] == "1.2.27", "lock version lost"
    assert identity["plugin_installed_version"] == "1.18.5", "installed version lost"
    remediation = str(identity["remediation"]).lower()
    assert "restart" in remediation, "stale diagnostics should recommend restart"
    assert "reinstall" in remediation, "stale diagnostics should recommend reinstall"


def test_opencode_identity_reads_bun_generated_lockfile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "opencode"
    version = "1.18.21"
    _write_identity_metadata(
        config_dir,
        IdentityVersions(declared=version, locked=version, installed=version),
    )
    (config_dir / "bun.lock").write_text(
        """{
  "workspaces": {
    "": {
      "dependencies": {
        "@opencode-ai/plugin": "1.18.21",
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
        "matching runtime, manifest, lock, and installed versions should be compatible"
    )


@given(version=strategies.text(min_size=1, max_size=32))
def test_opencode_identity_is_compatible_when_all_observed_versions_match(
    version: str,
) -> None:
    assert _matching_identity_status(version) == "compatible", (
        "matching non-empty version observations must remain compatible"
    )


def test_opencode_identity_is_compatible_for_equivalent_version_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "opencode"
    _write_identity_metadata(
        config_dir,
        IdentityVersions(declared="^1.18.21", locked="1.18.21", installed="v1.18.21"),
    )
    monkeypatch.setattr(
        opencode_identity,
        "opencode_runtime_version",
        lambda: "opencode 1.18.21",
    )

    identity = _opencode.collect_opencode_install_identity(
        str(tmp_path / "slopgate"), config_dir=config_dir
    )

    assert identity["status"] == "compatible", (
        "range, prefix, and exact plugin versions should be treated as one identity"
    )
    assert identity["plugin_declared_version"] == "^1.18.21", (
        "declared specifier should remain the raw observed value"
    )


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
