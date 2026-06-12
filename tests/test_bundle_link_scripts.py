from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tests.support import SKIP_UNIX_ONLY

pytestmark = SKIP_UNIX_ONLY


REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOT = REPO_ROOT / "bundle"
VERIFY = BUNDLE_ROOT / "scripts" / "verify-local.sh"
UNLINK = BUNDLE_ROOT / "scripts" / "unlink-local.sh"
INTELLIGENT_SKILL = (
    BUNDLE_ROOT / "shared" / "skills" / "slopgate-intelligent-coding-patterns"
)


def run_script(
    script: Path, tmp_home: Path, *args: str
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(tmp_home)
    return subprocess.run(
        [str(script), *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def prepare_exact_and_legacy_links(tmp_home: Path) -> tuple[Path, Path, Path]:
    exact = tmp_home / ".claude" / "skills" / "slopgate-intelligent-coding-patterns"
    legacy = tmp_home / ".claude" / "skills" / "code-smell-utility-locator"
    legacy_target = tmp_home / "legacy" / "code-smell-utility-locator"
    exact.parent.mkdir(parents=True)
    legacy_target.mkdir(parents=True)
    exact.symlink_to(INTELLIGENT_SKILL, target_is_directory=True)
    legacy.symlink_to(legacy_target, target_is_directory=True)
    return exact, legacy, legacy_target


def assert_legacy_link_preserved(legacy: Path, legacy_target: Path) -> None:
    assert legacy.is_symlink(), "legacy non-bundle symlink should not be unlinked"
    assert legacy.resolve(strict=False) == legacy_target, (
        "legacy symlink target should remain unchanged"
    )


def test_verify_default_allows_mixed_migration_state_concisely(tmp_path: Path) -> None:
    result = run_script(VERIFY, tmp_path, "--only", "claude")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "WARN missing live path:" not in result.stdout
    assert "verify ok:" in result.stdout
    assert "warnings=" in result.stdout


def test_verify_strict_fails_when_manifest_destinations_are_not_exact_links(
    tmp_path: Path,
) -> None:
    result = run_script(VERIFY, tmp_path, "--only", "claude", "--strict")

    assert result.returncode != 0
    assert "FAIL missing live path:" in result.stdout
    assert "verify failed:" in result.stderr or "verify failed:" in result.stdout


def test_verify_accepts_exact_manifest_link_and_ignores_legacy_symlink(
    tmp_path: Path,
) -> None:
    exact, _, _ = prepare_exact_and_legacy_links(tmp_path)

    result = run_script(VERIFY, tmp_path, "--only", "claude", "--verbose")

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"OK {exact} -> {INTELLIGENT_SKILL}" in result.stdout
    assert "WARN existing non-bundle symlink:" not in result.stdout


def test_unlink_removes_only_exact_manifest_owned_symlinks(tmp_path: Path) -> None:
    exact, legacy, legacy_target = prepare_exact_and_legacy_links(tmp_path)

    result = run_script(UNLINK, tmp_path, "--only", "claude")

    assert result.returncode == 0, result.stdout + result.stderr
    assert not exact.exists(), "exact manifest-owned symlink should be removed"
    assert_legacy_link_preserved(legacy, legacy_target)
    assert "removed_or_would_remove=1" in result.stdout
