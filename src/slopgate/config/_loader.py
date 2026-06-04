from __future__ import annotations

from pathlib import Path

from slopgate.models import RuntimeConfig

from ._discovery import detect_root, resolve_config_path
from ._io import _load_json
from ._repo import ensure_worktree_enrollment, resolve_repo_root
from ._settings import _merge_config, ensure_trace_directories

def load_config(
    root: Path | None = None,
    repo_root: Path | None = None,
    *,
    ensure_enrollment: bool = True,
    ensure_trace: bool = True,
) -> RuntimeConfig:
    """Load configuration with XDG discovery chain.

    Config is loaded from resolve_config_path(). Root is used for
    trace directory and prompt context file resolution.
    """
    actual_root = (root or detect_root()).resolve()
    config_path = resolve_config_path()
    raw = _load_json(config_path)
    enrollment_root = ensure_worktree_enrollment(repo_root) if ensure_enrollment else None
    resolved_repo_root = enrollment_root or resolve_repo_root(repo_root) or (
        repo_root.resolve() if repo_root is not None else Path.cwd().resolve()
    )
    config = _merge_config(actual_root, raw, resolved_repo_root)
    if ensure_trace:
        ensure_trace_directories(config)
    return config
