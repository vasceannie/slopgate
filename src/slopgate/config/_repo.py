from __future__ import annotations

import subprocess
from pathlib import Path

from slopgate.util import warning

from ._coerce import _bool_value, _object_dict
from ._io import _load_toml, _slopgate_path, _slopgate_template, _write_slopgate

# Sentinel filenames that disable the quality gate for a repo.
_DISABLE_SENTINELS = (".noslopgate", ".no-slop-gate")

def _git_output(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 3,
) -> str | None:
    """Run a git command and return stripped stdout on success."""
    try:
        output = subprocess.check_output(
            args,
            cwd=str(cwd) if cwd is not None else None,
            text=True,
            timeout=timeout,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    stripped = output.strip()
    return stripped or None


def resolve_git_root(start: Path | None = None) -> Path | None:
    """Resolve the current git working tree root, if any."""
    path = (start or Path.cwd()).resolve()
    base = path if path.is_dir() else path.parent
    root = _git_output(
        ["git", "-C", str(base), "rev-parse", "--show-toplevel"],
        cwd=base,
        timeout=3,
    )
    return Path(root).resolve() if root else None


def resolve_main_git_repo_root(start: Path | None = None) -> Path | None:
    """Resolve the main repo root for a git repo or worktree."""
    git_root = resolve_git_root(start)
    if git_root is None:
        return None
    common_dir = _git_output(
        ["git", "-C", str(git_root), "rev-parse", "--git-common-dir"],
        cwd=git_root,
        timeout=3,
    )
    if common_dir is None:
        return git_root
    common_path = Path(common_dir)
    if not common_path.is_absolute():
        common_path = (git_root / common_path).resolve()
    else:
        common_path = common_path.resolve()
    return common_path.parent.resolve()

def list_git_worktrees(repo_root: Path) -> list[Path]:
    """List all known worktree roots for *repo_root*."""
    main_repo_root = resolve_main_git_repo_root(repo_root) or repo_root.resolve()
    output = _git_output(
        ["git", "-C", str(main_repo_root), "worktree", "list", "--porcelain"],
        cwd=main_repo_root,
        timeout=5,
    )
    if output is None:
        return []
    worktrees: list[Path] = []
    for line in output.splitlines():
        if not line.startswith("worktree "):
            continue
        worktree_path = Path(line.replace("worktree ", "", 1)).resolve()
        if worktree_path not in worktrees:
            worktrees.append(worktree_path)
    return worktrees


def ensure_worktree_enrollment(start: Path | None = None) -> Path | None:
    """Copy the main repo quality gate into a worktree when inherited."""
    path = (start or Path.cwd()).resolve()
    repo_root = resolve_repo_root(path)
    if repo_root is not None:
        return repo_root

    worktree_root = resolve_git_root(path)
    if worktree_root is None:
        return None

    main_repo_root = resolve_main_git_repo_root(worktree_root)
    if main_repo_root is None or main_repo_root == worktree_root:
        return None

    source_marker = _slopgate_path(main_repo_root)
    if not source_marker.exists():
        return None

    try:
        template = source_marker.read_text(encoding="utf-8")
        _write_slopgate(worktree_root, template)
    except OSError as exc:
        warning(
            "worktree enrollment copy failed",
            worktree=str(worktree_root),
            source=str(source_marker),
            error=str(exc),
        )
        return None
    return worktree_root


def enroll_repo(
    start: Path | None = None,
    *,
    include_worktrees: bool = True,
) -> tuple[Path, list[Path]]:
    """Enroll a repo and optionally propagate the marker to existing worktrees."""
    target = (start or Path.cwd()).resolve()
    default_root = target if target.is_dir() else target.parent
    repo_root = resolve_main_git_repo_root(target) or default_root

    template = _slopgate_template()
    written_roots: list[Path] = []
    if _write_slopgate(repo_root, template):
        written_roots.append(repo_root)
    else:
        try:
            template = _slopgate_path(repo_root).read_text(encoding="utf-8")
        except OSError:
            template = _slopgate_template()

    if include_worktrees and resolve_main_git_repo_root(repo_root) is not None:
        for worktree_root in list_git_worktrees(repo_root):
            if worktree_root == repo_root:
                continue
            if _write_slopgate(worktree_root, template):
                written_roots.append(worktree_root)

    return repo_root, written_roots



def resolve_repo_root(start: Path | None = None) -> Path | None:
    """Resolve enrolled repo root by walking ancestors from *start*."""
    path = (start or Path.cwd()).resolve()
    for candidate in (path, *path.parents):
        if (candidate / "slopgate.toml").exists():
            return candidate
    return None


def is_repo_enrolled(repo_root: Path | None = None) -> bool:
    """Return True when *repo_root* (or one ancestor) is enrolled."""
    return resolve_repo_root(repo_root) is not None


def is_repo_disabled(repo_root: Path | None = None) -> bool:
    """Check if the quality gate is disabled for a repo."""
    if repo_root is None:
        repo_root = Path.cwd().resolve()
    else:
        repo_root = repo_root.resolve()

    for sentinel in _DISABLE_SENTINELS:
        if (repo_root / sentinel).exists():
            return True

    toml_data = _load_toml(repo_root)
    qg_section = _object_dict(toml_data.get("slopgate", {}))
    if _bool_value(qg_section.get("enabled"), True) is False:
        return True

    return False


def is_path_skipped(repo_path: Path, skip_paths: list[str]) -> bool:
    """Check if *repo_path* matches any glob in the central skip_paths list."""
    import fnmatch

    resolved = str(repo_path.resolve())
    for pattern in skip_paths:
        if fnmatch.fnmatch(resolved, pattern):
            return True
    return False
