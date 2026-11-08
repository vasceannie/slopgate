from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import slopgate.installer._suite
from slopgate.constants import PLATFORM_CLAUDE
from tests.support import SKIP_LINUX_ONLY, SKIP_WINDOWS_ONLY
from tests.test_suite_autoupdate import patch_linux_installer_config_dirs

PI_INDEX_CONTENT = "export default function () {}\n"
PI_INDEX_DIGEST = hashlib.sha256(PI_INDEX_CONTENT.encode("utf-8")).hexdigest()
PI_MANIFEST: dict[str, object] = {
    "schema_version": 1,
    "platform": "pi",
    "files": {"index.ts": PI_INDEX_DIGEST},
}
INVALID_PI_MANIFESTS = [
    pytest.param("{not json", "malformed manifest", id="malformed"),
    pytest.param("{}", "empty manifest", id="empty"),
    pytest.param(
        json.dumps({**PI_MANIFEST, "files": {}}), "empty file map", id="empty-files"
    ),
    pytest.param(
        json.dumps({**PI_MANIFEST, "platform": "omp"}),
        "foreign platform",
        id="foreign-platform",
    ),
    pytest.param(
        json.dumps({**PI_MANIFEST, "files": {"index.ts": "0" * 64}}),
        "digest mismatch",
        id="digest-mismatch",
    ),
    pytest.param(
        json.dumps({**PI_MANIFEST, "files": {"gone.ts": PI_INDEX_DIGEST}}),
        "missing listed file",
        id="missing-file",
    ),
]


def _prepare_linux_discovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    patch_linux_installer_config_dirs(monkeypatch, tmp_path)
    monkeypatch.setattr(slopgate.installer._suite.shutil, "which", lambda _name: None)
    return tmp_path


def _create_pi_staging(
    home: Path,
) -> tuple[Path, Path, dict[str, object]]:
    staging = home / ".local" / "share" / "slopgate" / "native" / "pi"
    package = staging / "package"
    manifest = package / ".slopgate-owned.json"
    package.mkdir(parents=True)
    (package / "index.ts").write_text(PI_INDEX_CONTENT, encoding="utf-8")
    return staging, manifest, PI_MANIFEST


@SKIP_LINUX_ONLY
def test_discover_install_sites_detects_current_device_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_linux_discovery(tmp_path, monkeypatch)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".config" / "opencode").mkdir(parents=True)

    sites = slopgate.installer._suite.discover_install_sites()

    assert [(site.platform, site.present) for site in sites] == [
        (PLATFORM_CLAUDE, True),
        ("opencode", True),
    ], "discovery should use the configured current device home"


@SKIP_LINUX_ONLY
def test_discover_install_sites_lists_missing_host_staging_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _prepare_linux_discovery(tmp_path, monkeypatch)

    sites = slopgate.installer._suite.discover_install_sites(include_missing=True)

    assert (
        [site.platform for site in sites],
        [site.path for site in sites if site.platform in {"pi", "omp"}],
    ) == (
        [PLATFORM_CLAUDE, "codex", "opencode", "cursor", "pi", "omp"],
        [
            home / ".local" / "share" / "slopgate" / "native" / "pi",
            home / ".local" / "share" / "slopgate" / "native" / "omp",
        ],
    ), "include_missing should list every harness and native staging root"


@SKIP_LINUX_ONLY
def test_discover_install_sites_detects_native_clis_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_linux_discovery(tmp_path, monkeypatch)
    monkeypatch.setattr(
        slopgate.installer._suite.shutil,
        "which",
        lambda name: f"/sandbox/bin/{name}"
        if name in {"claude", "codex", "opencode", "cursor-agent", "pi", "omp"}
        else None,
    )

    sites = slopgate.installer._suite.discover_install_sites()

    assert [(site.platform, site.present) for site in sites] == [
        ("claude", True),
        ("codex", True),
        ("opencode", True),
        ("cursor", True),
        ("pi", True),
        ("omp", True),
    ], "every harness should be discoverable from its executable on PATH"


@SKIP_LINUX_ONLY
def test_discover_install_sites_rejects_absent_staging_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _prepare_linux_discovery(tmp_path, monkeypatch)
    _create_pi_staging(home)

    assert slopgate.installer._suite.discover_install_sites() == [], (
        "an absent ownership manifest must not count as Slopgate-owned staging"
    )


@SKIP_LINUX_ONLY
@pytest.mark.parametrize(("content", "case"), INVALID_PI_MANIFESTS)
def test_discover_install_sites_rejects_invalid_staging_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: str,
    case: str,
) -> None:
    home = _prepare_linux_discovery(tmp_path, monkeypatch)
    _staging, manifest, _pi_manifest = _create_pi_staging(home)
    manifest.write_text(content, encoding="utf-8")

    assert slopgate.installer._suite.discover_install_sites() == [], (
        f"{case} must not count as Slopgate-owned staging"
    )


@SKIP_LINUX_ONLY
def test_discover_install_sites_detects_valid_owned_staging_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _prepare_linux_discovery(tmp_path, monkeypatch)
    staging, manifest, pi_manifest = _create_pi_staging(home)
    manifest.write_text(json.dumps(pi_manifest), encoding="utf-8")

    sites = slopgate.installer._suite.discover_install_sites()

    assert [(site.platform, site.path) for site in sites] == [("pi", staging)], (
        "a matching Pi ownership manifest should make Pi discoverable"
    )


@SKIP_WINDOWS_ONLY
def test_discover_install_sites_respects_windows_appdata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(slopgate.installer._suite.shutil, "which", lambda _name: None)
    appdata = tmp_path / "AppData" / "Roaming"
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / ".claude").mkdir()
    (appdata / "opencode").mkdir(parents=True)

    sites = slopgate.installer._suite.discover_install_sites()

    assert [(site.platform, site.present) for site in sites] == [
        (PLATFORM_CLAUDE, True),
        ("opencode", True),
    ], "Windows discovery should use APPDATA for roaming configuration"
