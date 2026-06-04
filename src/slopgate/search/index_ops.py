"""Local index discovery and resolution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from slopgate._types import ObjectDict, object_dict, string_value
from slopgate.search.config import (
    DEFAULT_INDEXES_PATH,
    IsxError,
    SearchConfig,
    expand,
)
from slopgate.search.git_utils import (
    get_git_remote_url,
    get_git_repo_root,
    urls_match,
)


def _read_index_metadata(path: Path) -> ObjectDict | None:
    try:
        raw_data = cast(object, json.loads(path.read_text()))
    except (OSError, json.JSONDecodeError):
        return None
    return object_dict(raw_data)


def local_indexes(_cfg: SearchConfig) -> list[ObjectDict]:
    """Scan ``~/.local/share/islands/indexes/`` for metadata.json files."""
    indexes_root = expand(None, DEFAULT_INDEXES_PATH)
    if not indexes_root.exists():
        return []

    items: list[ObjectDict] = []
    for path in indexes_root.glob("*/*/*/metadata.json"):
        data = _read_index_metadata(path)
        if data is not None:
            items.append(data)
    items.sort(key=lambda item: string_value(item.get("name")) or "")
    return items


def find_local_index(cfg: SearchConfig, target: str) -> ObjectDict | None:
    """Find a local index by name, full_name, or clone URL."""
    normalized = target.strip()
    for item in local_indexes(cfg):
        repo = object_dict(item.get("repository"))
        exact_candidates = {
            string_value(item.get("name")) or "",
            string_value(repo.get("full_name")) or "",
            string_value(repo.get("name")) or "",
        }
        if normalized in exact_candidates:
            return item
        url_candidates = [
            string_value(repo.get("clone_url")),
            string_value(repo.get("ssh_url")),
        ]
        for candidate in url_candidates:
            if urls_match(normalized, candidate):
                return item
    return None


def _resolve_current_repo_target(
    cfg: SearchConfig, cwd: Path | None
) -> tuple[str | None, str]:
    repo_root = get_git_repo_root(cwd)
    if not repo_root:
        raise IsxError(
            (
                "could not resolve '.': not inside a git working tree. "
                "Pass a repo URL or index name instead."
            )
        )
    clone_url = get_git_remote_url(repo_root)
    if not clone_url:
        raise IsxError(
            (
                f"git repo at {repo_root} has no 'origin' remote. "
                "Pass the clone URL explicitly."
            )
        )
    for item in local_indexes(cfg):
        repo = object_dict(item.get("repository"))
        if urls_match(string_value(repo.get("clone_url")), clone_url):
            return string_value(item.get("name")), clone_url
    return None, clone_url


def _resolve_index_name(item: ObjectDict) -> tuple[str | None, str]:
    repo = object_dict(item.get("repository"))
    clone_url = string_value(repo.get("clone_url"))
    if not clone_url:
        raise IsxError(f"index {item.get('name')} is missing repository.clone_url")
    return string_value(item.get("name")), clone_url


def _unknown_target_error(cfg: SearchConfig, normalized: str) -> IsxError:
    known = ", ".join(
        string_value(item.get("name")) or "" for item in local_indexes(cfg)[:8]
    )
    if known:
        return IsxError(
            f"could not resolve target: {normalized}. Known indexes: {known}"
        )
    return IsxError(f"could not resolve target: {normalized}")


def resolve_reindex_target(
    cfg: SearchConfig, target: str, cwd: Path | None = None
) -> tuple[str | None, str]:
    """Resolve a reindex target to ``(index_name_or_None, clone_url)``."""
    normalized = target.strip()
    if not normalized:
        raise IsxError("index or repo target is required")

    if normalized == ".":
        return _resolve_current_repo_target(cfg, cwd)

    item = find_local_index(cfg, normalized)
    if item:
        return _resolve_index_name(item)

    if "://" in normalized or normalized.startswith("git@"):
        return None, normalized

    raise _unknown_target_error(cfg, normalized)
