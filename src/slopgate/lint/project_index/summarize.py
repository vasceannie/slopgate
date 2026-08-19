"""Summarize project files from parse attempts or disk."""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path

from slopgate.lint._helpers.models import FileParseAttempt, PARSE_ERROR_KIND_READ
from slopgate.lint.project_index.facts import facts_to_json
from slopgate.lint.project_index.models import ProjectFileSummary


@dataclass(frozen=True, slots=True)
class _IndexedSource:
    size: int
    mtime_ns: int
    source: str
    content_hash: str
    tree: ast.Module | None


def sorted_project_paths(
    src_files: tuple[Path, ...], test_files: tuple[Path, ...]
) -> tuple[tuple[Path, str], ...]:
    """Return resolved project paths tagged as source or test."""
    keyed: dict[Path, str] = {}
    for path in src_files:
        keyed[path.resolve()] = "source"
    for path in test_files:
        keyed[path.resolve()] = "test"
    return tuple(sorted(keyed.items(), key=lambda item: str(item[0])))


def index_root(request_root: Path, paths: tuple[Path, ...]) -> Path:
    """Return a root that contains every indexed path."""
    root = request_root.resolve()
    resolved_paths = tuple(path.resolve() for path in paths)
    if not resolved_paths or all(path.is_relative_to(root) for path in resolved_paths):
        return root
    common_parent = resolved_paths[0].parent
    for path in resolved_paths[1:]:
        common_parent = _common_parent(common_parent, path.parent)
    return common_parent


def attempt_lookup(
    attempts: tuple[FileParseAttempt, ...] | None,
) -> dict[Path, FileParseAttempt]:
    """Index parse attempts by resolved path."""
    if attempts is None:
        return {}
    return {attempt.path.resolve(): attempt for attempt in attempts}


def summarize_project_file(
    root: Path,
    path: Path,
    kind: str,
    attempts_by_path: dict[Path, FileParseAttempt],
) -> ProjectFileSummary | None:
    """Build compact metadata for one file, preferring a retained parse attempt."""
    attempt = attempts_by_path.get(path.resolve())
    if attempt is not None:
        return _summarize_attempt(root, path, kind, attempt)
    return _summarize_from_disk(root, path, kind)


def summary_payload_size(summary: ProjectFileSummary) -> int:
    """Return encoded size of persisted summary strings."""
    return sum(
        len(part.encode("utf-8"))
        for part in (
            summary.relative_path,
            summary.content_hash,
            summary.duplicate_fingerprint,
            *summary.symbols,
            *summary.imports,
            facts_to_json(summary.facts),
        )
    )


def dirty_relative_paths(root: Path, dirty_paths: tuple[Path, ...]) -> tuple[str, ...]:
    """Return sorted POSIX paths for dirty files under *root*."""
    return tuple(
        sorted(
            {
                path.resolve().relative_to(root).as_posix()
                for path in dirty_paths
                if path.resolve().is_relative_to(root)
            }
        )
    )


def _common_parent(left: Path, right: Path) -> Path:
    left_parts = left.resolve().parts
    right_parts = right.resolve().parts
    common_parts: list[str] = []
    for left_part, right_part in zip(left_parts, right_parts):
        if left_part != right_part:
            break
        common_parts.append(left_part)
    return Path(*common_parts) if common_parts else Path(left.anchor or right.anchor)


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


def _summary_from_source(
    root: Path, path: Path, kind: str, indexed: _IndexedSource
) -> ProjectFileSummary:
    normalized = "\n".join(
        line.strip() for line in indexed.source.splitlines() if line.strip()
    )
    return ProjectFileSummary(
        path=path,
        relative_path=path.relative_to(root).as_posix(),
        kind=kind,
        size=indexed.size,
        mtime_ns=indexed.mtime_ns,
        content_hash=indexed.content_hash,
        symbols=_symbol_names(indexed.tree),
        imports=_import_names(indexed.tree),
        duplicate_fingerprint=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
    )


def _summarize_attempt(
    root: Path, path: Path, kind: str, attempt: FileParseAttempt
) -> ProjectFileSummary | None:
    if attempt.error is not None and attempt.error.kind == PARSE_ERROR_KIND_READ:
        return None
    tree = attempt.parsed.tree if attempt.parsed is not None else None
    summary = _summary_from_source(
        root,
        path,
        kind,
        _IndexedSource(
            size=attempt.size,
            mtime_ns=attempt.mtime_ns,
            source=attempt.source,
            content_hash=attempt.content_hash,
            tree=tree,
        ),
    )
    return _with_extracted_facts(summary, attempt)


def _parse_source(path: Path, source: str) -> ast.Module | None:
    try:
        return ast.parse(source, filename=str(path))
    except SyntaxError:
        return None


def _summarize_from_disk(
    root: Path, path: Path, kind: str
) -> ProjectFileSummary | None:
    try:
        stat = path.stat()
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return _summary_from_source(
        root,
        path,
        kind,
        _IndexedSource(
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            source=source,
            content_hash=hashlib.sha256(source.encode("utf-8")).hexdigest(),
            tree=_parse_source(path, source),
        ),
    )


def _with_extracted_facts(
    summary: ProjectFileSummary, attempt: FileParseAttempt
) -> ProjectFileSummary:
    if attempt.parsed is None:
        return summary
    from dataclasses import replace

    from slopgate.lint.project_index.extract import extract_file_facts
    from slopgate.lint.project_index.integrity_facts import attach_integrity_facts

    facts = attach_integrity_facts(attempt.parsed, extract_file_facts(attempt.parsed))
    return replace(summary, facts=facts)
