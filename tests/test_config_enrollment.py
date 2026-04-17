from __future__ import annotations

import subprocess
from pathlib import Path

from vibeforcer.config import enroll_repo


def _init_git_repo_with_worktree(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    worktree = tmp_path / "repo-worktree"
    repo.mkdir()

    _ = subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    _ = subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    _ = subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    _ = (repo / "README.md").write_text("root\n", encoding="utf-8")
    _ = subprocess.run(
        ["git", "add", "."],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    _ = subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    _ = subprocess.run(
        ["git", "worktree", "add", "-b", "feature/enroll", str(worktree)],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return repo, worktree


def test_enroll_repo_propagates_to_existing_worktrees(tmp_path: Path) -> None:
    repo, worktree = _init_git_repo_with_worktree(tmp_path)

    repo_root, written_roots = enroll_repo(worktree)

    assert repo_root == repo
    assert set(written_roots) == {repo, worktree}
    assert (repo / "quality_gate.toml").exists()
    assert (worktree / "quality_gate.toml").exists()
