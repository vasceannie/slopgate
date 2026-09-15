from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = REPO_ROOT / "scripts" / "gitnexus"
LOCAL_BINARY = Path.home() / ".local" / "bin" / "gitnexus"


def _write_fake_binary(tmp_path: Path) -> Path:
    binary = tmp_path / "gitnexus"
    binary.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n", encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def _run_wrapper(
    binary: Path, cwd: Path, *arguments: str
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["GITNEXUS_BIN"] = str(binary)
    return subprocess.run(
        [str(WRAPPER), *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_wrapper_rejects_a_self_referential_local_binary(tmp_path: Path) -> None:
    result = _run_wrapper(WRAPPER, tmp_path, "status")

    assert result.returncode == 1, "wrapper recursion must fail closed"
    assert result.stdout == "", f"self-reference wrote stdout: {result.stdout}"
    assert result.stderr == f"GitNexus binary resolves to wrapper: {WRAPPER}\n", (
        "self-reference failure must identify the recursion target"
    )


def test_wrapper_delegates_arguments_to_configured_local_binary(tmp_path: Path) -> None:
    binary = _write_fake_binary(tmp_path)

    result = _run_wrapper(binary, tmp_path, "impact", "symbol", "--repo", ".")

    assert result.returncode == 0, f"local GitNexus delegation failed: {result.stderr}"
    assert result.stdout.splitlines() == ["impact", "symbol", "--repo", "."], (
        "wrapper must preserve every argument passed to the local executable"
    )
    assert result.stderr == "", f"successful delegation wrote stderr: {result.stderr}"


def test_wrapper_fails_when_local_binary_is_missing(tmp_path: Path) -> None:
    binary = tmp_path / "missing-gitnexus"

    result = _run_wrapper(binary, tmp_path, "status")

    assert result.returncode == 1, "missing local executable must fail closed"
    assert result.stdout == "", f"missing executable wrote stdout: {result.stdout}"
    assert result.stderr == f"GitNexus binary is not executable: {binary}\n", (
        "missing executable failure must identify the configured local path"
    )


def test_wrapper_fails_when_local_binary_is_not_executable(tmp_path: Path) -> None:
    binary = tmp_path / "gitnexus"
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    result = _run_wrapper(binary, tmp_path, "status")

    assert result.returncode == 1, "non-executable local install must fail closed"
    assert result.stdout == "", f"non-executable binary wrote stdout: {result.stdout}"
    assert result.stderr == f"GitNexus binary is not executable: {binary}\n", (
        "non-executable failure must identify the configured local path"
    )


@pytest.mark.skipif(
    not os.access(LOCAL_BINARY, os.X_OK),
    reason="local GitNexus installation is unavailable on this host",
)
def test_wrapper_uses_the_host_local_install(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.pop("GITNEXUS_BIN", None)

    wrapped = subprocess.run(
        [str(WRAPPER), "--version"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    direct = subprocess.run(
        [str(LOCAL_BINARY), "--version"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert wrapped.returncode == direct.returncode == 0, (
        f"wrapper/local execution differed: wrapper={wrapped.stderr!r}, local={direct.stderr!r}"
    )
    assert wrapped.stdout == direct.stdout, (
        "wrapper must expose the installed local GitNexus version unchanged"
    )
    assert wrapped.stderr == direct.stderr, (
        "wrapper must preserve stderr from the local GitNexus executable"
    )


def test_wrapper_is_executable_and_shell_syntax_is_valid() -> None:
    assert WRAPPER.stat().st_mode & stat.S_IXUSR, "wrapper must be executable"

    result = subprocess.run(
        ["bash", "-n", str(WRAPPER)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, f"wrapper has invalid shell syntax: {result.stderr}"
