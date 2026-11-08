from __future__ import annotations

import json
from pathlib import Path

import pytest

import slopgate
from slopgate.installer.native.model import VERSION_KEY
from slopgate.installer.native.packages import (
    MARKETPLACE_NAME,
    OWNERSHIP_MANIFEST_NAME,
    MarketplaceSpec,
    StagingError,
    check_staging_owned,
    marketplace_plan,
    staging_is_current,
)
from tests.native.packages_support import (
    BASE_VERSION,
    CATALOG_DIR,
    HOST_NAME,
    NEXT_VERSION,
    PLUGIN_NAME,
    package_plan_for as _package_plan,
    renderer as _renderer,
    staged_plan as _staged_plan,
    write_manifest_key as _write_manifest_key,
)


def _version_change_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[bool, bool, bool, bool, bool]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(slopgate, "__version__", BASE_VERSION)
    spec = MarketplaceSpec(
        CATALOG_DIR, PLUGIN_NAME, "test enforcement plugin", _renderer
    )
    old_plan = marketplace_plan(HOST_NAME, spec)
    monkeypatch.setattr(slopgate, "__version__", NEXT_VERSION)
    new_plan = marketplace_plan(HOST_NAME, spec)
    catalog = json.loads(new_plan.files[f"{CATALOG_DIR}/marketplace.json"])
    package_prefix = new_plan.package_dir.relative_to(new_plan.entry_root).as_posix()
    old_index = (
        f"{old_plan.package_dir.relative_to(old_plan.entry_root).as_posix()}/index.ts"
    )
    new_index = f"{package_prefix}/index.ts"
    manifest_path = f"{package_prefix}/package.json"
    manifest = json.loads(new_plan.files[manifest_path])
    return (
        old_plan.files[old_index] == new_plan.files[new_index],
        old_plan.package_dir != new_plan.package_dir,
        manifest[VERSION_KEY] == new_plan.version,
        catalog["plugins"][0][VERSION_KEY] == new_plan.version,
        new_plan.version.startswith(f"{NEXT_VERSION}+local."),
    )


def test_marketplace_plan_digest_is_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    spec = MarketplaceSpec(
        CATALOG_DIR, PLUGIN_NAME, "test enforcement plugin", _renderer
    )

    first = marketplace_plan(HOST_NAME, spec)
    second = marketplace_plan(HOST_NAME, spec)
    catalog = json.loads(first.files[f"{CATALOG_DIR}/marketplace.json"])
    observed = (
        first.version,
        first.files,
        first.package_dir,
        catalog["name"],
    )

    assert observed == (
        second.version,
        second.files,
        second.package_dir,
        MARKETPLACE_NAME,
    ), "identical renderer inputs should produce one stable immutable snapshot"


def test_version_only_change_creates_consistent_new_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = _version_change_observation(tmp_path, monkeypatch)

    assert observed == (True, True, True, True, True), (
        "a Slopgate version-only change should keep extension bytes but version the new catalog snapshot consistently"
    )


def test_check_staging_owned_accepts_valid_staged_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _staged_plan(tmp_path, monkeypatch)
    check_staging_owned(plan)
    observed = (
        staging_is_current(plan),
        (plan.entry_root / OWNERSHIP_MANIFEST_NAME).is_file(),
    )

    assert observed == (True, True), (
        "a valid staging manifest should verify and match the current package plan"
    )


def test_staging_manifest_rejects_malformed_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _staged_plan(tmp_path, monkeypatch)
    (plan.entry_root / OWNERSHIP_MANIFEST_NAME).write_text("{", encoding="utf-8")

    with pytest.raises(StagingError, match="unreadable ownership manifest"):
        check_staging_owned(plan)


def test_staging_manifest_rejects_foreign_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _staged_plan(tmp_path, monkeypatch)
    manifest_path = plan.entry_root / OWNERSHIP_MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["platform"] = "other-host"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(StagingError, match="foreign or malformed"):
        check_staging_owned(plan)


def test_staging_manifest_rejects_tampered_managed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _staged_plan(tmp_path, monkeypatch)
    (plan.entry_root / "index.ts").write_text("tampered", encoding="utf-8")

    with pytest.raises(StagingError, match="modified Slopgate staging file"):
        check_staging_owned(plan)


def test_staging_manifest_rejects_missing_managed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _staged_plan(tmp_path, monkeypatch)
    (plan.entry_root / "index.ts").unlink()

    with pytest.raises(StagingError, match="modified Slopgate staging file"):
        check_staging_owned(plan)


def test_staging_manifest_rejects_unexpected_file_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _staged_plan(tmp_path, monkeypatch)
    _write_manifest_key(plan, "unexpected.txt")

    with pytest.raises(StagingError, match="modified Slopgate staging file"):
        check_staging_owned(plan)


@pytest.mark.parametrize("key", ["../escape.txt", "/etc/passwd", "a/../../escape", ""])
def test_staging_manifest_rejects_unsafe_relative_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    plan = _staged_plan(tmp_path, monkeypatch)
    _write_manifest_key(plan, key)

    with pytest.raises(StagingError, match="unsafe ownership manifest path"):
        check_staging_owned(plan)


def test_staging_manifest_rejects_symlinked_managed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _staged_plan(tmp_path, monkeypatch)
    managed = plan.entry_root / "index.ts"
    target = tmp_path / "outside.ts"
    target.write_bytes(managed.read_bytes())
    managed.unlink()
    managed.symlink_to(target)

    with pytest.raises(StagingError, match="symlink"):
        check_staging_owned(plan)


def test_staging_manifest_rejects_symlinked_entry_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _package_plan(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir(parents=True)
    plan.contain_root.mkdir(parents=True)
    plan.entry_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(StagingError, match="install through a symlink"):
        check_staging_owned(plan)
