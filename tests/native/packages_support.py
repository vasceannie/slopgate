"""Plan builders and staging probes shared by native package tests."""

from __future__ import annotations

import json
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from slopgate.installer.native.model import VERSION_KEY
from slopgate.installer.native.packages import (
    OWNERSHIP_MANIFEST_NAME,
    PackagePlan,
    StagingSnapshot,
    package_plan,
    snapshot_staging,
    write_staging,
)
from tests.native.environment import isolate_native_data_dirs

HOST_NAME = "claude-test"
PLUGIN_NAME = "test-enforcement"
BASE_VERSION = "2.4.2"
NEXT_VERSION = "2.4.3"
CATALOG_DIR = ".test-plugin"
FILE_DIGEST_WIDTH = 64
ORIGINAL_MODE = 0o640
MUTATED_MODE = stat.S_IREAD


def renderer(version: str) -> dict[str, str]:
    """Render a minimal single-plugin payload for *version*."""
    manifest = {VERSION_KEY: version, "name": PLUGIN_NAME}
    return {
        "index.ts": "export const enforcement = true;\n",
        "package.json": json.dumps(manifest, sort_keys=True) + "\n",
    }


def tree_bytes(root: Path) -> dict[str, bytes]:
    """Map every file below *root* to its bytes, keyed by relative path."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def package_plan_for(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PackagePlan:
    """Build a stable-path package plan with isolated HOME and Windows data roots."""
    isolate_native_data_dirs(monkeypatch, tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    return package_plan(HOST_NAME, render=renderer)


def staged_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PackagePlan:
    """Build a package plan and commit its staged payload and manifest."""
    plan = package_plan_for(tmp_path, monkeypatch)
    write_staging(plan)
    return plan


def write_manifest_key(plan: PackagePlan, key: str) -> None:
    """Add one ownership manifest entry that no staged file backs."""
    manifest_path = plan.entry_root / OWNERSHIP_MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][key] = "0" * FILE_DIGEST_WIDTH
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def staging_restore_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[PackagePlan, Path, dict[str, bytes], StagingSnapshot]:
    """Snapshot a staged package whose entry file has a known writable mode."""
    plan = staged_plan(tmp_path, monkeypatch)
    index = plan.entry_root / "index.ts"
    index.chmod(ORIGINAL_MODE)
    before = tree_bytes(plan.entry_root)
    snapshot = snapshot_staging(plan)
    return plan, index, before, snapshot


def empty_ownership_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[PackagePlan, dict[str, bytes]]:
    """Create nonempty foreign staging with a schema-valid empty file map."""
    plan = staged_plan(tmp_path, monkeypatch)
    manifest_path = plan.entry_root / OWNERSHIP_MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = {}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (plan.entry_root / "foreign.txt").write_bytes(b"foreign content")
    return plan, tree_bytes(plan.entry_root)


def empty_staging_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[PackagePlan, StagingSnapshot]:
    """Snapshot a package plan before anything is staged."""
    plan = package_plan_for(tmp_path, monkeypatch)
    return plan, snapshot_staging(plan)


def inject_probe_failure(
    monkeypatch: pytest.MonkeyPatch, plan: PackagePlan, failure_site: str
) -> None:
    """Make one ownership-probe filesystem call raise for *failure_site*."""
    manifest_path = plan.entry_root / OWNERSHIP_MANIFEST_NAME
    managed_file = plan.entry_root / "index.ts"
    if failure_site == "manifest_check":
        original_is_file = Path.is_file

        def fail_manifest(path: Path) -> bool:
            if path == manifest_path:
                raise OSError("injected manifest probe failure")
            return original_is_file(path)

        monkeypatch.setattr(Path, "is_file", fail_manifest)
    elif failure_site == "directory_listing":
        original_listing = Path.iterdir

        def fail_listing(path: Path) -> Iterator[Path]:
            if path == plan.entry_root:
                raise OSError("injected directory listing failure")
            return original_listing(path)

        monkeypatch.setattr(Path, "iterdir", fail_listing)
    else:
        original_read = Path.read_bytes

        def fail_file_read(path: Path) -> bytes:
            if path == managed_file:
                raise OSError("injected managed file read failure")
            return original_read(path)

        monkeypatch.setattr(Path, "read_bytes", fail_file_read)
