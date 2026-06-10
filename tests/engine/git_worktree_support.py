"""Git worktree helpers for engine integration tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__ = [
    "init_git_worktree",
    "fake_slopgate_worktree_git_output",
    "_fake_non_default_slopgate_git_output",
]


def init_git_worktree(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    worktree = tmp_path / "repo-worktree"
    repo.mkdir()
    _ = (repo / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
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
        ["git", "add", "."], cwd=repo, check=True, capture_output=True, text=True
    )
    _ = subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    _ = subprocess.run(
        ["git", "worktree", "add", "-b", "feature/worktree-support", str(worktree)],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return (repo, worktree)


def fake_slopgate_worktree_git_output(
    args: list[str], cwd: Path | None = None, timeout: int = 3
) -> str | None:
    if args[-3:] == ["remote", "get-url", "origin"]:
        return "https://lab.baked.rocks/claude/slopgate.git"
    if args[-2:] == ["branch", "--show-current"]:
        return "feature/worktree-support"
    if args[-2:] == ["symbolic-ref", "refs/remotes/origin/HEAD"]:
        return "refs/remotes/origin/feature/worktree-support"
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return result.stdout.strip() or None


_fake_non_default_slopgate_git_output = fake_slopgate_worktree_git_output
