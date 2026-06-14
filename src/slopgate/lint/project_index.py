"""Deterministic compact project metadata index for lint analysis."""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_INDEX_CACHE_MAX_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ProjectIndexRequest:
    """Inputs for one deterministic project index build."""

    root: Path
    src_files: tuple[Path, ...]
    test_files: tuple[Path, ...]
    dirty_paths: tuple[Path, ...] = ()
    max_bytes: int = PROJECT_INDEX_CACHE_MAX_BYTES


@dataclass(frozen=True, slots=True)
class ProjectFileSummary:
    """Compact metadata for one indexed project file."""

    path: Path
    relative_path: str
    kind: str
    size: int
    mtime_ns: int
    content_hash: str
    symbols: tuple[str, ...]
    imports: tuple[str, ...]
    duplicate_fingerprint: str


@dataclass(frozen=True, slots=True)
class ProjectIndex:
    """Deterministic project file inventory for hook and CLI lint surfaces."""

    root: Path
    files: tuple[ProjectFileSummary, ...]
    dirty_paths: tuple[str, ...]
    bytes_used: int
    max_bytes: int
    by_relative_path: dict[str, ProjectFileSummary] = field(repr=False)


def build_project_index(request: ProjectIndexRequest) -> ProjectIndex:
    """Build a sorted, compact, deterministic project metadata index."""

    project_paths = _sorted_project_paths(request.src_files, request.test_files)
    root = _index_root(request.root, tuple(path for path, _ in project_paths))
    summaries: list[ProjectFileSummary] = []
    bytes_used = 0
    for path, kind in project_paths:
        summary = _summarize_project_file(root, path, kind)
        if summary is None:
            continue
        summary_size = sum(
            len(part.encode("utf-8"))
            for part in (
                summary.relative_path,
                summary.content_hash,
                summary.duplicate_fingerprint,
                *summary.symbols,
                *summary.imports,
            )
        )
        if bytes_used + summary_size > request.max_bytes:
            continue
        summaries.append(summary)
        bytes_used += summary_size
    dirty_paths = tuple(
        sorted(
            {
                path.resolve().relative_to(root).as_posix()
                for path in request.dirty_paths
                if path.resolve().is_relative_to(root)
            }
        )
    )
    return ProjectIndex(
        root=root,
        files=tuple(summaries),
        dirty_paths=dirty_paths,
        bytes_used=bytes_used,
        max_bytes=request.max_bytes,
        by_relative_path={summary.relative_path: summary for summary in summaries},
    )


def _index_root(request_root: Path, paths: tuple[Path, ...]) -> Path:
    root = request_root.resolve()
    resolved_paths = tuple(path.resolve() for path in paths)
    if not resolved_paths or all(path.is_relative_to(root) for path in resolved_paths):
        return root
    common_parent = resolved_paths[0].parent
    for path in resolved_paths[1:]:
        common_parent = _common_parent(common_parent, path.parent)
    return common_parent


def _common_parent(left: Path, right: Path) -> Path:
    left_parts = left.resolve().parts
    right_parts = right.resolve().parts
    common_parts: list[str] = []
    for left_part, right_part in zip(left_parts, right_parts):
        if left_part != right_part:
            break
        common_parts.append(left_part)
    return Path(*common_parts) if common_parts else Path(left.anchor or right.anchor)


def _sorted_project_paths(
    src_files: tuple[Path, ...], test_files: tuple[Path, ...]
) -> tuple[tuple[Path, str], ...]:
    keyed: dict[Path, str] = {}
    for path in src_files:
        keyed[path.resolve()] = "source"
    for path in test_files:
        keyed[path.resolve()] = "test"
    return tuple(sorted(keyed.items(), key=lambda item: str(item[0])))


def _summarize_project_file(
    root: Path, path: Path, kind: str
) -> ProjectFileSummary | None:
    try:
        stat = path.stat()
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    tree = _parse_source(path, source)
    source_bytes = source.encode("utf-8")
    normalized = "\n".join(line.strip() for line in source.splitlines() if line.strip())
    return ProjectFileSummary(
        path=path,
        relative_path=path.relative_to(root).as_posix(),
        kind=kind,
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        content_hash=hashlib.sha256(source_bytes).hexdigest(),
        symbols=_symbol_names(tree),
        imports=_import_names(tree),
        duplicate_fingerprint=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
    )


def _parse_source(path: Path, source: str) -> ast.Module | None:
    try:
        return ast.parse(source, filename=str(path))
    except SyntaxError:
        return None


def _symbol_names(tree: ast.Module | None) -> tuple[str, ...]:
    if tree is None:
        return ()
    names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    return tuple(sorted(names))


def _import_names(tree: ast.Module | None) -> tuple[str, ...]:
    if tree is None:
        return ()
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return tuple(sorted(imports))


__all__ = [
    "ProjectFileSummary",
    "ProjectIndex",
    "ProjectIndexRequest",
    "build_project_index",
]
