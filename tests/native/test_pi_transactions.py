from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

import pytest

import slopgate
import slopgate.installer.native.packages
import slopgate.installer.native.pi.install
from slopgate.constants import INSTALL_SCOPE_USER
from slopgate.installer._shared import ContainedWrite
from slopgate.installer.native.commands import REMOVE_SUBCOMMAND, NativeCommandError
from slopgate.installer.native.model import NativeRequest
from tests.native.pi_support import (
    PiHarness,
    make_harness,
    native_mutations,
    original_artifacts_match,
    registered_sources,
    seed_legacy,
)

FIRST_WRITE_COUNT = 1
FAILING_WRITE_COUNT = 2
REFRESHED_VERSION = "2.4.3"


def _staging_snapshot(
    root: Path,
) -> tuple[bool, tuple[str, ...], dict[str, tuple[bytes, int]]]:
    if not root.exists():
        return False, (), {}
    directories = tuple(
        sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_dir())
    )
    files = {
        str(path.relative_to(root)): (
            path.read_bytes(),
            stat.S_IMODE(path.stat().st_mode),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    return True, directories, files


def _fail_second_staged_write(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[Path], list[Path]]:
    original = slopgate.installer.native.packages.write_contained_text
    attempts: list[Path] = []
    committed: list[Path] = []

    def write_staged_file(target: Path, content: str, policy: ContainedWrite) -> Path:
        attempts.append(target)
        if len(attempts) == FAILING_WRITE_COUNT:
            raise OSError("injected later staging write failure")
        written = original(target, content, policy)
        committed.append(written)
        return written

    monkeypatch.setattr(
        slopgate.installer.native.packages, "write_contained_text", write_staged_file
    )
    return attempts, committed


@dataclass(frozen=True, slots=True)
class _PartialWriteObservation:
    status: int
    first_write_committed: bool
    staging_restored: bool
    legacy_restored: bool
    registrations_restored: bool
    mutations_unchanged: bool


def _prepare_existing_package(
    existing_staging: bool,
    harness: PiHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not existing_staging:
        return
    status = harness.install(install_scope=INSTALL_SCOPE_USER)
    if status != 0:
        raise AssertionError(
            "already-staged scenario setup should register the initial package"
        )
    monkeypatch.setattr(slopgate, "__version__", REFRESHED_VERSION)


def _partial_staging_observation(
    existing_staging: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> _PartialWriteObservation:
    harness = make_harness(tmp_path, monkeypatch)
    _prepare_existing_package(existing_staging, harness, monkeypatch)
    legacy = seed_legacy(harness, INSTALL_SCOPE_USER)
    staging_root = harness.package_root.parent
    staging_before = _staging_snapshot(staging_root)
    registrations_before = registered_sources(harness)
    mutations_before = native_mutations(harness.fake)
    attempts, committed = _fail_second_staged_write(monkeypatch)
    status = harness.install(install_scope=INSTALL_SCOPE_USER)
    return _PartialWriteObservation(
        status,
        len(attempts) == FAILING_WRITE_COUNT and len(committed) == FIRST_WRITE_COUNT,
        _staging_snapshot(staging_root) == staging_before,
        original_artifacts_match(legacy),
        registered_sources(harness) == registrations_before,
        native_mutations(harness.fake) == mutations_before,
    )


@pytest.mark.parametrize(
    "existing_staging",
    (False, True),
    ids=("absent-package", "already-staged-package"),
)
def test_partial_staging_transaction_restores_all_prior_state(
    existing_staging: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = _partial_staging_observation(existing_staging, tmp_path, monkeypatch)

    assert observed.status == 1, (
        "a later staged write failure must abort the install transaction"
    )
    assert (
        observed.first_write_committed,
        observed.staging_restored,
        observed.legacy_restored,
        observed.registrations_restored,
        observed.mutations_unchanged,
    ) == (True, True, True, True, True), (
        "partial staging failure must restore committed bytes, topology, prior "
        "enforcement, registrations, and native state"
    )


@dataclass(frozen=True, slots=True)
class _FailedInstallObservation:
    status: int
    output: str
    package_staged: bool
    user_registrations: int


def _fail_native_removals(monkeypatch: pytest.MonkeyPatch) -> None:
    original = slopgate.installer.native.pi.install.run_pi_command

    def run_pi(argv: list[str], request: NativeRequest) -> str:
        if REMOVE_SUBCOMMAND in argv:
            raise NativeCommandError("injected remove failure")
        return original(argv, request)

    monkeypatch.setattr(slopgate.installer.native.pi.install, "run_pi_command", run_pi)


def _failed_install_observation(
    removal_fails: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _FailedInstallObservation:
    harness = make_harness(tmp_path, monkeypatch)
    harness.fake.fail("install", INSTALL_SCOPE_USER, mutate_before_failure=True)
    if removal_fails:
        _fail_native_removals(monkeypatch)
    status = harness.install(install_scope=INSTALL_SCOPE_USER)
    output = capsys.readouterr().out
    return _FailedInstallObservation(
        status,
        output,
        harness.package_root.exists(),
        len(registered_sources(harness)[0]),
    )


@pytest.mark.parametrize(
    ("removal_fails", "package_kept"),
    ((True, True), (False, False)),
    ids=("removal-fails-keeps-package", "removal-succeeds-restores-staging"),
)
def test_rollback_restores_staging_only_after_registrations_are_compensated(
    removal_fails: bool,
    package_kept: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed = _failed_install_observation(removal_fails, tmp_path, monkeypatch, capsys)

    assert observed.status == 1, "an install failing after registration must fail"
    assert observed.package_staged is package_kept, (
        "the staged package must remain while its registration cannot be removed "
        "and be restored once compensation succeeds"
    )
    assert (observed.user_registrations, "Incomplete rollback:" in observed.output) == (
        (1, True) if removal_fails else (0, False)
    ), "incomplete compensation must leave the registration and be reported"
