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


def _run_wrapper(wrapper: Path, *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(wrapper), "--version"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_wrapper_accepts_the_pinned_canonical_version() -> None:
    if not os.access(CANONICAL_BINARY, os.X_OK):
        raise unittest.SkipTest("canonical GitNexus binary is unavailable on this host")

    result = _run_wrapper(WRAPPER, cwd=Path("/tmp"))

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == VERSION_FILE.read_text(encoding="utf-8").strip()
    assert result.stderr == ""


def test_wrapper_fails_closed_when_the_pin_does_not_match(tmp_path: Path) -> None:
    copied_root = tmp_path / "repo"
    copied_scripts = copied_root / "scripts"
    copied_scripts.mkdir(parents=True)
    copied_wrapper = copied_scripts / "gitnexus"
    shutil.copy2(WRAPPER, copied_wrapper)
    copied_wrapper.chmod(copied_wrapper.stat().st_mode | stat.S_IXUSR)
    (copied_root / ".gitnexus-version").write_text("0.0.0\n", encoding="utf-8")

    result = _run_wrapper(copied_wrapper, cwd=tmp_path)

    assert result.returncode != 0
    assert "version mismatch" in result.stderr.lower()
    assert result.stdout == ""


def test_wrapper_does_not_leak_environment_values_on_failure(tmp_path: Path) -> None:
    copied_root = tmp_path / "repo"
    copied_scripts = copied_root / "scripts"
    copied_scripts.mkdir(parents=True)
    copied_wrapper = copied_scripts / "gitnexus"
    shutil.copy2(WRAPPER, copied_wrapper)
    copied_wrapper.chmod(copied_wrapper.stat().st_mode | stat.S_IXUSR)
    (copied_root / ".gitnexus-version").write_text("0.0.0\n", encoding="utf-8")
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

    assert secret not in result.stdout + result.stderr


def test_wrapper_is_executable_and_shell_syntax_is_valid() -> None:
    assert WRAPPER.stat().st_mode & stat.S_IXUSR
    result = subprocess.run(
        ["bash", "-n", str(WRAPPER)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_wrapper_uses_only_the_fixed_absolute_binary() -> None:
    source = WRAPPER.read_text(encoding="utf-8")

    assert source.startswith("#!/bin/bash\n")
    assert 'GITNEXUS_BIN="/home/trav/.local/bin/gitnexus"' in source
    assert 'exec "${GITNEXUS_BIN}" "$@"' in source
    fallback_tokens = ("npx", "pnpm", "bunx", "command -v", "which ")
    forbidden_fallbacks = [fallback for fallback in fallback_tokens if fallback in source]
    assert forbidden_fallbacks == []
