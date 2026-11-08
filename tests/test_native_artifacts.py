from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies

from slopgate.installer._omp_support import (
    MANIFEST_PAYLOAD,
    OMP_OWNERSHIP_MARKERS,
    OmpManifestExtensions,
    OmpManifestPayload,
    is_owned_omp_index,
    is_owned_omp_manifest,
    omp_extension_has_owned_slopgate,
)
from slopgate.installer._shared import UnsafeInstallPathError
from slopgate.installer.native.artifacts import (
    ArtifactSnapshot,
    capture_artifact,
    missing_directories,
    remove_empty_directories,
    restore_artifact,
    unsafe_anchor_issue,
)

ORIGINAL_MODE = 0o640
REPLACEMENT_MODE = 0o600
EXECUTABLE_MODE = 0o755
MAX_PROPERTY_BYTES = 64
PROPERTY_EXAMPLES = 12
RESTORE_CONTENTS = strategies.binary(max_size=MAX_PROPERTY_BYTES)
RESTORE_MODES = strategies.sampled_from((ORIGINAL_MODE, EXECUTABLE_MODE))


def _restore_case(
    tmp_path_factory: pytest.TempPathFactory, content: bytes, mode: int
) -> tuple[Path, ArtifactSnapshot, int]:
    """Return a mutated target, its snapshot, and the mode the platform reports."""
    tmp_path = tmp_path_factory.mktemp("restore-artifact")
    target = tmp_path / "property-managed.txt"
    target.write_bytes(content + b"\x00")
    target.chmod(REPLACEMENT_MODE)
    return (
        target,
        ArtifactSnapshot(True, content, mode),
        _reference_mode(tmp_path, mode),
    )


def test_capture_artifact_preserves_original_bytes_and_mode(tmp_path: Path) -> None:
    target = tmp_path / "managed.txt"
    target.write_bytes(b"original bytes")
    target.chmod(ORIGINAL_MODE)
    reported_mode = stat.S_IMODE(target.stat().st_mode)

    snapshot = capture_artifact(target)

    assert snapshot == ArtifactSnapshot(True, b"original bytes", reported_mode), (
        "capture should retain the original file bytes and permission bits"
    )


@settings(max_examples=PROPERTY_EXAMPLES, deadline=None)
@given(content=RESTORE_CONTENTS, mode=RESTORE_MODES)
def test_restore_artifact_property_restores_original_bytes_and_mode(
    tmp_path_factory: pytest.TempPathFactory, content: bytes, mode: int
) -> None:
    target, snapshot, expected_mode = _restore_case(tmp_path_factory, content, mode)
    restore_artifact(target, snapshot)
    observed = (target.read_bytes(), stat.S_IMODE(target.stat().st_mode))

    assert observed == (content, expected_mode), (
        "artifact restoration should recover arbitrary original bytes and modes"
    )


def _read_only_target(tmp_path: Path) -> tuple[Path, int]:
    """Create a mutated read-only artifact and return it with its reported mode."""
    target = tmp_path / "read-only.txt"
    target.write_bytes(b"mutated")
    target.chmod(stat.S_IREAD)
    return target, stat.S_IMODE(target.stat().st_mode)


def _reference_mode(directory: Path, mode: int = ORIGINAL_MODE) -> int:
    """Mode the platform reports after chmod(mode) on a fresh file."""
    reference = directory / "reference.txt"
    reference.write_bytes(b"")
    reference.chmod(mode)
    return stat.S_IMODE(reference.stat().st_mode)


def _failing_write(_path: Path, _data: bytes) -> int:
    raise OSError("injected write failure")


def test_restore_artifact_overwrites_read_only_file_and_restores_mode(
    tmp_path: Path,
) -> None:
    target, _ = _read_only_target(tmp_path)

    restore_artifact(target, ArtifactSnapshot(True, b"original", ORIGINAL_MODE))

    observed = (target.read_bytes(), stat.S_IMODE(target.stat().st_mode))
    assert observed == (b"original", _reference_mode(tmp_path)), (
        "rollback must overwrite a read-only file and reapply the captured mode"
    )


def test_restore_artifact_write_failure_leaves_prior_mode_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target, prior_mode = _read_only_target(tmp_path)
    monkeypatch.setattr(Path, "write_bytes", _failing_write)

    with pytest.raises(OSError, match="injected write failure"):
        restore_artifact(target, ArtifactSnapshot(True, b"original", ORIGINAL_MODE))

    assert stat.S_IMODE(target.stat().st_mode) == prior_mode, (
        "a failed rollback write must not leave the temporary write bit behind"
    )


def test_restore_missing_snapshot_removes_created_file(tmp_path: Path) -> None:
    target = tmp_path / "created-during-transaction.txt"
    target.write_bytes(b"temporary")

    restore_artifact(target, ArtifactSnapshot(False, None, None))

    assert not target.exists(), (
        "rollback should remove a file absent before the transaction"
    )


def test_capture_artifact_refuses_directory_instead_of_reading_it(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "not-a-file"
    directory.mkdir()

    with pytest.raises(UnsafeInstallPathError, match="non-file artifact"):
        capture_artifact(directory)


def test_missing_directories_and_empty_cleanup_are_transaction_safe(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    deepest = existing / "one" / "two"

    missing = missing_directories(deepest)
    created = (existing / "one" / "two", existing / "one")
    created[0].mkdir(parents=True)
    cleanup_status = remove_empty_directories(missing)

    assert missing == created, (
        "missing directory candidates should be ordered deepest-first"
    )
    assert cleanup_status == 0, (
        "empty transaction-created directories should be removed"
    )
    assert not (existing / "one").exists(), (
        "cleanup should stop at the pre-existing anchor"
    )


def test_remove_empty_directories_reports_nonempty_path(tmp_path: Path) -> None:
    directory = tmp_path / "nonempty"
    directory.mkdir()
    (directory / "keep.txt").write_text("user data", encoding="utf-8")

    status = remove_empty_directories((directory,))

    assert status == 1, "cleanup should report a directory it cannot safely remove"
    assert (directory / "keep.txt").exists(), (
        "cleanup must preserve unknown sibling data"
    )


def test_unsafe_anchor_issue_accepts_missing_anchor(tmp_path: Path) -> None:
    anchor = tmp_path / ".omp"

    issue = unsafe_anchor_issue(anchor)

    assert issue is None, (
        "a missing project config directory is safe before native setup"
    )


def test_unsafe_anchor_issue_rejects_file_anchor(tmp_path: Path) -> None:
    anchor = tmp_path / ".omp"
    anchor.write_text("not a directory", encoding="utf-8")

    issue = unsafe_anchor_issue(anchor)

    assert issue is not None and "non-directory" in issue, (
        "a file at the native project anchor must be rejected"
    )


def test_unsafe_anchor_issue_rejects_symlink_anchor(tmp_path: Path) -> None:
    destination = tmp_path / "destination"
    destination.mkdir()
    anchor = tmp_path / ".omp"
    anchor.symlink_to(destination, target_is_directory=True)

    issue = unsafe_anchor_issue(anchor)

    assert issue is not None and "symlinked" in issue, (
        "native writes must not follow a symlinked project anchor"
    )


def _owned_omp_index() -> str:
    return "\n".join(OMP_OWNERSHIP_MARKERS)


def _owned_omp_manifest() -> OmpManifestPayload:
    extensions: OmpManifestExtensions = {"extensions": ["./index.ts"]}
    return {
        "name": "omp-slopgate",
        "private": True,
        "type": "module",
        "omp": extensions,
        "peerDependencies": {
            "@oh-my-pi/pi-coding-agent": "*",
            "@oh-my-pi/pi-tui": "*",
        },
    }


def _write_owned_omp_package(tmp_path: Path) -> tuple[Path, Path]:
    package_dir = tmp_path / "omp-slopgate"
    package_dir.mkdir()
    index_path = package_dir / "index.ts"
    manifest_path = package_dir / "package.json"
    index_path.write_text(_owned_omp_index(), encoding="utf-8")
    manifest_path.write_text(json.dumps(MANIFEST_PAYLOAD), encoding="utf-8")
    return index_path, manifest_path


def test_omp_manifest_types_and_ownership_predicates() -> None:
    manifest = json.dumps(_owned_omp_manifest())
    observed = (
        is_owned_omp_index(_owned_omp_index()),
        is_owned_omp_manifest(manifest),
    )

    assert observed == (True, True), (
        "canonical OMP index and manifest payloads should be recognized as owned"
    )


def test_omp_manifest_predicate_rejects_malformed_json() -> None:
    assert not is_owned_omp_manifest("{"), (
        "malformed OMP manifest JSON must not be treated as Slopgate-owned"
    )


def test_omp_extension_markers_are_detected_in_managed_files(
    tmp_path: Path,
) -> None:
    index_path, manifest_path = _write_owned_omp_package(tmp_path)
    observed = (
        omp_extension_has_owned_slopgate(index_path),
        omp_extension_has_owned_slopgate(manifest_path),
    )

    assert observed == (True, True), (
        "OMP legacy detection should find ownership markers in index and manifest files"
    )
