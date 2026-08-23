from __future__ import annotations

import argparse
import json
from pathlib import Path

from slopgate.cli.io import string_arg
from slopgate.constants import METADATA_PATH
from slopgate.models import RuntimeConfig


def _check_roots(target: Path) -> tuple[Path | None, Path | None, Path | None]:
    from slopgate.config import (
        resolve_git_root,
        resolve_main_git_repo_root,
        resolve_repo_root,
    )

    resolved_repo_root = resolve_repo_root(target)
    git_root = resolve_git_root(target)
    main_repo_root = resolve_main_git_repo_root(target)
    return resolved_repo_root, git_root, main_repo_root


def _check_skip_state(
    target: Path,
    config: RuntimeConfig,
    resolved_repo_root: Path | None,
) -> tuple[bool, bool]:
    from slopgate.config import is_path_skipped

    base_dir = target if target.is_dir() else target.parent
    target_skipped = is_path_skipped(target, config.skip_paths, base_dir=base_dir)
    repo_skipped = (
        resolved_repo_root is not None
        and is_path_skipped(resolved_repo_root, config.skip_paths, base_dir=base_dir)
    )
    return target_skipped, repo_skipped


def _check_report(target: Path, config: RuntimeConfig) -> dict[str, object]:
    from slopgate.config import is_repo_disabled

    resolved_repo_root, git_root, main_repo_root = _check_roots(target)
    disabled = resolved_repo_root is not None and is_repo_disabled(resolved_repo_root)
    target_skipped, repo_skipped = _check_skip_state(
        target, config, resolved_repo_root
    )
    status = (
        "NOT_ENROLLED"
        if resolved_repo_root is None
        else "SKIPPED"
        if target_skipped
        else "RELAXED"
        if disabled
        else "ENROLLED"
    )
    return {
        METADATA_PATH: str(target),
        "status": status,
        "resolved_repo_root": str(resolved_repo_root)
        if resolved_repo_root is not None
        else None,
        "git_root": str(git_root) if git_root is not None else None,
        "main_repo_root": str(main_repo_root)
        if main_repo_root is not None
        else None,
        "repo_disabled": disabled,
        "enforcement_mode": (
            "outside_repo"
            if resolved_repo_root is None
            else "repo_relaxed" if disabled else "repo_strict"
        ),
        "path_skipped": target_skipped,
        "target_path_skipped": target_skipped,
        "repo_path_skipped": repo_skipped,
        "skip_paths": config.skip_paths,
    }


def cmd_check(args: argparse.Namespace) -> int:
    from slopgate.config import load_config

    target = Path(string_arg(args, METADATA_PATH, ".")).resolve()
    config = load_config(repo_root=target, ensure_enrollment=False, ensure_trace=False)
    print(json.dumps(_check_report(target, config), indent=2))
    return 0
