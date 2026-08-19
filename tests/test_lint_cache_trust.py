from __future__ import annotations

from pathlib import Path

from slopgate.lint.project_index.cache_trust import cache_path_is_trusted
from tests.lint_paths_support import run_test_git


def test_untracked_cache_path_is_trusted(tmp_path: Path) -> None:
    run_test_git(tmp_path, "init", "-b", "main")

    assert cache_path_is_trusted(
        tmp_path, tmp_path / ".slopgate/cache/lint-index.sqlite"
    )


def test_tracked_cache_path_is_untrusted(tmp_path: Path) -> None:
    run_test_git(tmp_path, "init", "-b", "main")
    cache_path = tmp_path / ".slopgate/cache/lint-index.sqlite"
    cache_path.parent.mkdir(parents=True)
    cache_path.touch()
    run_test_git(tmp_path, "add", "-f", ".slopgate/cache")

    assert not cache_path_is_trusted(tmp_path, cache_path)


def test_symlinked_cache_path_is_untrusted(tmp_path: Path) -> None:
    run_test_git(tmp_path, "init", "-b", "main")
    target = tmp_path / "external-cache"
    target.mkdir()
    metadata = tmp_path / ".slopgate"
    metadata.mkdir()
    (metadata / "cache").symlink_to(target, target_is_directory=True)

    assert not cache_path_is_trusted(
        tmp_path, metadata / "cache/lint-index.sqlite"
    )


def test_cache_path_is_untrusted_when_git_provenance_fails(tmp_path: Path) -> None:
    assert not cache_path_is_trusted(
        tmp_path, tmp_path / ".slopgate/cache/lint-index.sqlite"
    )
