from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, strategies
import pytest

from slopgate.search import index_ops
from slopgate.search.config import SearchConfig
from slopgate.search.index_ops import (
    find_local_index,
    local_indexes,
    resolve_reindex_target,
)

TARGETS = strategies.text(alphabet="abcxyz-/_.", min_size=1, max_size=20)


@dataclass(frozen=True)
class IndexCase:
    owner: str = "acme"
    repo: str = "alpha"
    name: str = "alpha-index"
    clone_url: str = "https://github.com/acme/alpha.git"


def write_index(root: Path, case: IndexCase) -> None:
    metadata = {
        "name": case.name,
        "repository": {
            "name": case.repo,
            "full_name": f"{case.owner}/{case.repo}",
            "clone_url": case.clone_url,
            "ssh_url": f"git@github.com:{case.owner}/{case.repo}.git",
        },
    }
    path = root / case.owner / case.repo / case.name / "metadata.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata), encoding="utf-8")


def test_local_indexes_reads_sorted_metadata_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_index(
        tmp_path,
        IndexCase(repo="beta", name="zeta", clone_url="https://github.com/acme/beta.git"),
    )
    write_index(tmp_path, IndexCase(name="alpha"))
    monkeypatch.setattr(index_ops, "DEFAULT_INDEXES_PATH", tmp_path)

    indexes = local_indexes(SearchConfig())

    assert [item["name"] for item in indexes] == ["alpha", "zeta"]


def test_find_local_index_matches_name_full_name_and_urls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_index(tmp_path, IndexCase())
    monkeypatch.setattr(index_ops, "DEFAULT_INDEXES_PATH", tmp_path)
    cfg = SearchConfig()

    matches = {
        "name": find_local_index(cfg, "alpha-index"),
        "full_name": find_local_index(cfg, "acme/alpha"),
        "ssh": find_local_index(cfg, "git@github.com:acme/alpha.git"),
    }

    assert {key: item["name"] if item else None for key, item in matches.items()} == {
        "name": "alpha-index",
        "full_name": "alpha-index",
        "ssh": "alpha-index",
    }


def test_resolve_reindex_target_accepts_index_names_and_repo_urls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clone_url = "https://github.com/acme/alpha.git"
    write_index(tmp_path, IndexCase(clone_url=clone_url))
    monkeypatch.setattr(index_ops, "DEFAULT_INDEXES_PATH", tmp_path)
    cfg = SearchConfig()

    resolved = {
        "index": resolve_reindex_target(cfg, "alpha-index"),
        "url": resolve_reindex_target(cfg, "https://github.com/acme/new.git"),
    }

    assert resolved == {
        "index": ("alpha-index", clone_url),
        "url": (None, "https://github.com/acme/new.git"),
    }


def test_resolve_reindex_target_rejects_unknown_names(tmp_path: Path) -> None:
    cfg = SearchConfig()

    with pytest.raises(index_ops.IsxError, match="could not resolve target"):
        resolve_reindex_target(cfg, "missing")


@given(TARGETS)
def test_find_local_index_returns_none_without_metadata_property(target: str) -> None:
    original = index_ops.DEFAULT_INDEXES_PATH
    with TemporaryDirectory() as raw_path:
        index_ops.DEFAULT_INDEXES_PATH = Path(raw_path)
        try:
            match = find_local_index(SearchConfig(), target)
        finally:
            index_ops.DEFAULT_INDEXES_PATH = original
    assert match is None


@given(TARGETS)
def test_resolve_reindex_target_accepts_url_targets_property(suffix: str) -> None:
    target = f"https://github.com/acme/{suffix.strip('/') or 'repo'}.git"

    resolved = resolve_reindex_target(SearchConfig(), target)

    assert resolved == (None, target)
