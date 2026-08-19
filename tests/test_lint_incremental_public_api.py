"""Source-only assemble contract for incremental lint facts."""

from __future__ import annotations

from pathlib import Path

from slopgate.lint.project_index.assemble import (
    block_violations,
    call_sequence_violations,
    clone_violations,
    literal_violations,
)
from slopgate.lint.project_index.facts import CloneFact, FileAnalysisFacts
from slopgate.lint.project_index.models import (
    ProjectFileSummary,
    ProjectIndex,
    ProjectIndexRequest,
)
from slopgate.quality.constant_index import ConstantIndex


def clone_summary(root: Path, relative: str, kind: str) -> ProjectFileSummary:
    clones = (CloneFact("shared-digest", "shared", 1),)
    return ProjectFileSummary(
        path=root / relative,
        relative_path=relative,
        kind=kind,
        size=1,
        mtime_ns=1,
        content_hash=kind,
        symbols=(),
        imports=(),
        duplicate_fingerprint="",
        facts=FileAnalysisFacts(semantic_clones=clones),
    )


def mixed_kind_index(root: Path) -> ProjectIndex:
    if not root.is_absolute():
        raise ValueError("root must be absolute")
    return ProjectIndex.from_summaries(
        root,
        ProjectIndexRequest(root=root, src_files=(), test_files=()),
        (
            clone_summary(root, "src/a.py", "source"),
            clone_summary(root, "tests/test_a.py", "test"),
        ),
        1,
    )


def test_clone_violations_ignore_matching_test_files(tmp_path: Path) -> None:
    assert clone_violations(mixed_kind_index(tmp_path)) == []


def test_block_violations_ignore_matching_test_files(tmp_path: Path) -> None:
    assert block_violations(mixed_kind_index(tmp_path)) == []


def test_call_sequence_violations_ignore_matching_test_files(tmp_path: Path) -> None:
    assert call_sequence_violations(mixed_kind_index(tmp_path)) == []


def test_literal_violations_empty_for_clone_facts(tmp_path: Path) -> None:
    constants = ConstantIndex(tmp_path, {}, ())
    assert literal_violations(mixed_kind_index(tmp_path), constants) == []
