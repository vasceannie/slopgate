from __future__ import annotations

__all__ = [
    "config_dir",
    "detect_root",
    "ensure_trace_directories",
    "ensure_worktree_enrollment",
    "enroll_repo",
    "is_path_skipped",
    "is_repo_disabled",
    "is_repo_enrolled",
    "list_git_worktrees",
    "load_config",
    "resolve_config_path",
    "resolve_git_root",
    "resolve_main_git_repo_root",
    "resolve_repo_root",
]

from ._discovery import config_dir, detect_root, resolve_config_path
from ._loader import load_config
from ._repo import (
    ensure_worktree_enrollment,
    enroll_repo,
    is_path_skipped,
    is_repo_disabled,
    is_repo_enrolled,
    list_git_worktrees,
    resolve_git_root,
    resolve_main_git_repo_root,
    resolve_repo_root,
)
from ._settings import ensure_trace_directories

__all__ = [
    "config_dir",
    "detect_root",
    "ensure_trace_directories",
    "ensure_worktree_enrollment",
    "enroll_repo",
    "is_path_skipped",
    "is_repo_disabled",
    "is_repo_enrolled",
    "list_git_worktrees",
    "load_config",
    "resolve_config_path",
    "resolve_git_root",
    "resolve_main_git_repo_root",
    "resolve_repo_root",
]
