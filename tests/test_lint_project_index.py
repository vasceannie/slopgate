from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, strategies

from slopgate.lint._collector_groups.source import source_analysis
from slopgate.lint._config import load_config, reset_config
from slopgate.lint.project_index import (
    ProjectFileSummary,
    ProjectIndex,
    ProjectIndexRequest,
    build_project_index,
)


@given(
    source_name=strategies.text(
        alphabet=strategies.characters(whitelist_categories=("Ll",)),
        min_size=1,
        max_size=8,
    ),
    test_name=strategies.text(
        alphabet=strategies.characters(whitelist_categories=("Ll",)),
        min_size=1,
        max_size=8,
    ),
)
def test_project_index_deterministic_invariants(
    source_name: str, test_name: str
) -> None:
    assert _project_index_invariant_holds(source_name, test_name), (
        "ProjectIndex should produce sorted, stable metadata within its byte cap"
    )


def _write_named_project_files(
    root: Path, source_name: str, test_name: str
) -> tuple[Path, Path]:
    source = root / "src" / f"{source_name}.py"
    test = root / "tests" / f"test_{test_name}.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    test.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    test.write_text("def test_alpha():\n    assert True\n", encoding="utf-8")
    return source, test


def _project_index_invariant_holds(source_name: str, test_name: str) -> bool:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        source, test = _write_named_project_files(root, source_name, test_name)
        first = build_project_index(
            ProjectIndexRequest(root=root, src_files=(source,), test_files=(test,))
        )
        second = build_project_index(
            ProjectIndexRequest(root=root, src_files=(source,), test_files=(test,))
        )
    paths = tuple(summary.relative_path for summary in first.files)
    first_hashes = tuple(summary.content_hash for summary in first.files)
    second_hashes = tuple(summary.content_hash for summary in second.files)
    return (
        paths == tuple(sorted(paths))
        and first_hashes == second_hashes
        and first.bytes_used <= first.max_bytes
    )


def _write_project_files(root: Path) -> tuple[Path, Path]:
    source = root / "src" / "pkg" / "worker.py"
    test = root / "tests" / "test_worker.py"
    source.parent.mkdir(parents=True)
    test.parent.mkdir(parents=True)
    source.write_text(
        "import json\n\nclass Worker:\n    pass\n\ndef run():\n    return json.dumps({})\n",
        encoding="utf-8",
    )
    test.write_text(
        "from pkg.worker import run\n\ndef test_run():\n    assert run()\n",
        encoding="utf-8",
    )
    return source, test


def test_project_index_records_sorted_compact_file_metadata(tmp_path: Path) -> None:
    source, test = _write_project_files(tmp_path)

    index = build_project_index(
        ProjectIndexRequest(root=tmp_path, src_files=(source,), test_files=(test,))
    )
    source_summary = index.by_relative_path["src/pkg/worker.py"]

    assert {
        "index_type": isinstance(index, ProjectIndex),
        "summary_type": isinstance(source_summary, ProjectFileSummary),
        "relative_paths": tuple(summary.relative_path for summary in index.files),
        "source_kind": source_summary.kind,
        "source_symbols": source_summary.symbols,
        "source_imports": source_summary.imports,
        "hash_length": len(source_summary.content_hash),
    } == {
        "index_type": True,
        "summary_type": True,
        "relative_paths": ("src/pkg/worker.py", "tests/test_worker.py"),
        "source_kind": "source",
        "source_symbols": ("Worker", "run"),
        "source_imports": ("json",),
        "hash_length": 64,
    }


def test_project_index_tracks_dirty_paths_and_memory_cap(tmp_path: Path) -> None:
    source, test = _write_project_files(tmp_path)

    capped = build_project_index(
        ProjectIndexRequest(
            root=tmp_path,
            src_files=(source,),
            test_files=(test,),
            dirty_paths=(test,),
            max_bytes=1,
        )
    )

    assert {
        "files": capped.files,
        "dirty_paths": capped.dirty_paths,
        "bytes_used": capped.bytes_used,
        "max_bytes": capped.max_bytes,
    } == {
        "files": (),
        "dirty_paths": ("tests/test_worker.py",),
        "bytes_used": 0,
        "max_bytes": 1,
    }


def test_project_index_preserves_dirty_paths_outside_index_root(
    tmp_path: Path,
) -> None:
    source, test = _write_project_files(tmp_path / "repo")
    external_dirty = tmp_path / "external" / "generated.py"
    external_dirty.parent.mkdir(parents=True)
    external_dirty.write_text("VALUE = 1\n", encoding="utf-8")

    index = build_project_index(
        ProjectIndexRequest(
            root=tmp_path / "repo",
            src_files=(source,),
            test_files=(test,),
            dirty_paths=(external_dirty,),
        )
    )

    assert index.dirty_paths == ("../external/generated.py",), (
        "Dirty paths outside source/test common roots should remain visible"
    )


def test_project_index_preserves_dirty_only_paths(tmp_path: Path) -> None:
    dirty_path = tmp_path / "generated" / "worker.py"
    dirty_path.parent.mkdir(parents=True)
    dirty_path.write_text("VALUE = 1\n", encoding="utf-8")

    index = build_project_index(
        ProjectIndexRequest(
            root=tmp_path,
            src_files=(),
            test_files=(),
            dirty_paths=(dirty_path,),
        )
    )

    assert index.dirty_paths == ("generated/worker.py",), (
        "Dirty-only index builds should preserve their dirty path signal"
    )


def test_project_index_uses_file_common_root_for_external_inputs(
    tmp_path: Path,
) -> None:
    external_root = tmp_path / "external"
    source, test = _write_project_files(external_root)

    index = build_project_index(
        ProjectIndexRequest(root=Path.cwd(), src_files=(source,), test_files=(test,))
    )

    assert {
        "root": index.root,
        "relative_paths": tuple(summary.relative_path for summary in index.files),
    } == {
        "root": external_root,
        "relative_paths": ("src/pkg/worker.py", "tests/test_worker.py"),
    }


def test_source_analysis_returns_project_index_for_collector_surfaces(
    tmp_path: Path,
) -> None:
    source, test = _write_project_files(tmp_path)
    load_config(tmp_path)
    try:
        parsed_src, parsed_tests, oversized, literals, project_index = source_analysis(
            [source], [test]
        )
    finally:
        reset_config()

    assert {
        "src_count": len(parsed_src),
        "test_count": len(parsed_tests),
        "oversized": oversized,
        "literals": literals,
        "project_index_type": isinstance(project_index, ProjectIndex),
        "indexed_paths": tuple(
            summary.relative_path for summary in project_index.files
        ),
    } == {
        "src_count": 1,
        "test_count": 1,
        "oversized": [],
        "literals": [],
        "project_index_type": True,
        "indexed_paths": ("src/pkg/worker.py", "tests/test_worker.py"),
    }
