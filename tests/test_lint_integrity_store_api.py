"""Contracts for persisted suite IntegrityIndex round-trips."""

from __future__ import annotations

from pathlib import Path

from slopgate.lint.project_index.integrity_store import (
    load_integrity_index,
    load_or_build_integrity_index,
    save_integrity_index,
)
from slopgate.lint.project_index.models import ProjectIndex, ProjectIndexRequest
from slopgate.lint.project_index.store import connect_index


def _integrity_roundtrip(root: Path) -> set[str]:
    index = ProjectIndex.from_summaries(
        root,
        ProjectIndexRequest(root=root, src_files=(), test_files=()),
        (),
        0,
    )
    connection = connect_index(root)
    save_integrity_index(connection, index)
    connection.commit()
    loaded = load_integrity_index(connection, index)
    connection.close()
    rebuilt = load_or_build_integrity_index(index)
    return set() if loaded is None else rebuilt.module_names | loaded.module_names


def test_integrity_index_roundtrip_empty_modules(tmp_path: Path) -> None:
    assert _integrity_roundtrip(tmp_path) == set()
