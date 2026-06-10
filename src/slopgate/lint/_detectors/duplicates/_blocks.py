"""Detectors for code duplication."""

from __future__ import annotations
import ast
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING
from slopgate.lint._baseline import Violation
from slopgate.lint._config import get_config
from slopgate.lint._helpers import ParsedFile, ensure_parsed, find_source_files
from ..declarative import should_skip_block_window
from ..wrappers import call_name

if TYPE_CHECKING:
    pass
from ._semantic import (
    FUNC_TYPES,
    canonicalize_import_block,
    emit_group_violations,
    end_lineno,
    normalize_ast,
    skip_docstring,
    structure_hash,
)

MIN_BLOCK_SIZE = 3


def collect_block_windows(
    parsed: list[ParsedFile],
) -> dict[str, list[tuple[str, str, int, int]]]:
    """Hash sliding windows of consecutive statements across all scopes."""
    groups: dict[str, list[tuple[str, str, int, int]]] = defaultdict(list)
    for pf in parsed:
        for node in ast.walk(pf.tree):
            if isinstance(node, FUNC_TYPES):
                body, scope = (skip_docstring(node.body), node.name)
            elif isinstance(node, ast.Module):
                body, scope = (skip_docstring(node.body), "<module>")
            else:
                continue
            if len(body) < MIN_BLOCK_SIZE:
                continue
            _, canonical_import_indices = canonicalize_import_block(body)
            norms = [normalize_ast(stmt) for stmt in body]
            for i in range(len(norms) - MIN_BLOCK_SIZE + 1):
                window_indices = range(i, i + MIN_BLOCK_SIZE)
                if should_skip_block_window(
                    body, window_indices, scope, canonical_import_indices
                ):
                    continue
                h = structure_hash("|".join(norms[i : i + MIN_BLOCK_SIZE]))
                end = end_lineno(body[i + MIN_BLOCK_SIZE - 1], body[i].lineno)
                groups[h].append((pf.rel, scope, body[i].lineno, end))
    return groups


def detect_repeated_blocks(
    files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find blocks of consecutive statements that appear in multiple places."""
    parsed = ensure_parsed(files, fallback=find_source_files())
    groups = collect_block_windows(parsed)
    violations: list[Violation] = []
    for h, members in groups.items():
        if len(members) < 2:
            continue
        for rel, scope, start, end in members:
            violations.append(
                Violation(
                    rule="repeated-code-block",
                    relative_path=rel,
                    identifier=scope,
                    detail=f"lines {start}-{end}, block hash {h}",
                )
            )
    return violations


def extract_call_sequence(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[str, ...]:
    """Extract the ordered sequence of call target names from a function."""
    calls: list[tuple[int, str]] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        name = call_name(child)
        if not name:
            continue
        for prefix in ("self.", "cls."):
            if name.startswith(prefix):
                name = name[len(prefix) :]
                break
        calls.append((child.lineno, name))
    calls.sort(key=lambda c: c[0])
    return tuple((name for _, name in calls))


def detect_duplicate_call_sequences(
    files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find functions that make the same ordered sequence of calls."""
    cfg = get_config()
    min_len = cfg.min_call_sequence_length
    parsed = ensure_parsed(files, fallback=find_source_files())
    groups: dict[tuple[str, ...], list[tuple[str, str, int]]] = defaultdict(list)
    for pf in parsed:
        for node in ast.walk(pf.tree):
            if not isinstance(node, FUNC_TYPES):
                continue
            seq = extract_call_sequence(node)
            if len(seq) >= min_len:
                groups[seq].append((pf.rel, node.name, node.lineno))
    return emit_group_violations(
        "duplicate-call-sequence",
        groups,
        lambda seq, others: (
            f"calls [{', '.join(seq[:5])}{('...' if len(seq) > 5 else '')}], shared with {', '.join(others[:3])}"
        ),
    )
