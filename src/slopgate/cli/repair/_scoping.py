"""Scoped repair-state access, worktree validation, and generation clear."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import NamedTuple
from slopgate._types import ObjectDict

from slopgate.config import load_config
from slopgate.constants import WORKTREE_KEY
from slopgate.state import HookStateCorruptionError, HookStateStore


class _RepairScope(NamedTuple):
    store: HookStateStore
    root: Path
    required: ObjectDict | None


def _store(cwd: str, worktree: str | None = None) -> tuple[HookStateStore, Path]:
    from slopgate.cli.lint.commands import discover_project_root

    path_base = Path(cwd).resolve()
    if isinstance(worktree, str) and worktree.strip():
        worktree_path = Path(worktree)
        if not worktree_path.is_absolute():
            raise ValueError("repair worktree must be an absolute path")
        root = worktree_path.resolve()
    else:
        root = discover_project_root(path_base)
    if not path_base.is_relative_to(root):
        raise ValueError("repair cwd is outside the requested worktree")
    config = load_config(repo_root=root)
    store = HookStateStore(config.trace_dir, scope=str(root), path_base=path_base)
    return store, root


def _validate_repair_worktree(required: ObjectDict | None, root: Path) -> None:
    if required is None:
        return
    recorded = required.get(WORKTREE_KEY)
    if WORKTREE_KEY not in required:
        # Releases before worktree provenance wrote no worktree field at all. The
        # state file name is derived from the resolved scope, so a record found
        # here belongs to this worktree; rejecting it would leave the armed
        # generation unreadable and therefore unclearable.
        return
    if not isinstance(recorded, str) or recorded != str(root):
        raise ValueError("repair state worktree does not match requested worktree")


def _load_repair_scope(args: argparse.Namespace) -> _RepairScope:
    """Resolve the scoped store and pending generation for a repair command."""
    store, root = _store(args.cwd, getattr(args, "worktree", None))
    required = store.get_repair_required()
    _validate_repair_worktree(required, root)
    return _RepairScope(store, root, required)


def _invalid_repair_state(exc: HookStateCorruptionError | ValueError) -> int:
    print(json.dumps({"status": "REPAIR_STATE_INVALID", "reason": str(exc)}))
    return 2


def _release_repair_generation(store: HookStateStore, generation: str) -> int:
    """Clear *generation* under compare-and-set and report the outcome."""
    if not store.clear_repair_required(generation):
        print(json.dumps({"status": "generation_mismatch"}, sort_keys=True))
        return 1
    print(json.dumps({"status": "cleared", "generation": generation}))
    return 0
