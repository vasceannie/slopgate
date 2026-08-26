from __future__ import annotations

import os
import shutil
import stat
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = REPO_ROOT / "scripts" / "gitnexus"
VERSION_FILE = REPO_ROOT / ".gitnexus-version"
CANONICAL_BINARY = Path("/home/trav/.local/bin/gitnexus")


def _prepare_wrapper_fixture(
    tmp_path: Path,
    *,
    expected_version: str,
    actual_version: str,
) -> Path:
    copied_root = tmp_path / "repo"
    copied_scripts = copied_root / "scripts"
    copied_scripts.mkdir(parents=True)

    fake_binary = tmp_path / "gitnexus"
    fake_binary.write_text(
        f"#!/bin/sh\nprintf '%s\\n' '{actual_version}'\n",
        encoding="utf-8",
    )
    fake_binary.chmod(fake_binary.stat().st_mode | stat.S_IXUSR)

    copied_wrapper = copied_scripts / "gitnexus"
    shutil.copy2(WRAPPER, copied_wrapper)
    wrapper_source = copied_wrapper.read_text(encoding="utf-8")
    copied_wrapper.write_text(
        wrapper_source.replace(
            'GITNEXUS_BIN="/home/trav/.local/bin/gitnexus"',
            f'GITNEXUS_BIN="{fake_binary}"',
        ),
        encoding="utf-8",
    )
    copied_wrapper.chmod(copied_wrapper.stat().st_mode | stat.S_IXUSR)
    (copied_root / ".gitnexus-version").write_text(
        f"{expected_version}\n",
        encoding="utf-8",
    )
    return copied_wrapper


def test_wrapper_accepts_the_pinned_canonical_version() -> None:
    if not os.access(CANONICAL_BINARY, os.X_OK):
        raise unittest.SkipTest("canonical GitNexus binary is unavailable on this host")

    result = subprocess.run(
        [str(WRAPPER), "--version"],
        cwd=Path("/tmp"),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == VERSION_FILE.read_text(encoding="utf-8").strip()
    assert result.stderr == ""


def test_wrapper_fails_closed_when_the_pin_does_not_match(tmp_path: Path) -> None:
    copied_wrapper = _prepare_wrapper_fixture(
        tmp_path,
        expected_version="0.0.0",
        actual_version="1.6.10-rc.206",
    )

    result = subprocess.run(
        [str(copied_wrapper), "--version"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0, "wrapper should reject an unpinned binary version"
    assert "version mismatch" in result.stderr.lower(), (
        f"expected a version mismatch error, got: {result.stderr}"
    )
    assert result.stdout == "", f"failed validation should not write stdout: {result.stdout}"


def test_wrapper_does_not_leak_environment_values_on_failure(tmp_path: Path) -> None:
    copied_wrapper = _prepare_wrapper_fixture(
        tmp_path,
        expected_version="0.0.0",
        actual_version="1.6.10-rc.206",
    )
    secret = "wrapper-test-secret-must-not-appear"
    env = {**os.environ, "SLOPGATE_TEST_SECRET": secret}

    result = subprocess.run(
        [str(copied_wrapper), "--version"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert secret not in result.stdout + result.stderr, "environment secret leaked in wrapper output"


def test_wrapper_is_executable_and_shell_syntax_is_valid() -> None:
    assert WRAPPER.stat().st_mode & stat.S_IXUSR, "wrapper must be executable"
    result = subprocess.run(
        ["bash", "-n", str(WRAPPER)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"wrapper has invalid shell syntax: {result.stderr}"


def test_wrapper_uses_only_the_fixed_absolute_binary() -> None:
    source = WRAPPER.read_text(encoding="utf-8")

    assert source.startswith("#!/bin/bash\n"), "wrapper must use Bash"
    assert 'GITNEXUS_BIN="/home/trav/.local/bin/gitnexus"' in source, (
        "wrapper must use the fixed canonical binary path"
    )
    assert 'exec "${GITNEXUS_BIN}" "$@"' in source, "wrapper must forward arguments"
    fallback_tokens = ("npx", "pnpm", "bunx", "command -v", "which ")
    forbidden_fallbacks = [fallback for fallback in fallback_tokens if fallback in source]
    assert forbidden_fallbacks == [], f"unexpected fallback commands: {forbidden_fallbacks}"
