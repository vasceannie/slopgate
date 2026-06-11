"""Small repo-local lookup helpers for enrichment messages."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from slopgate.enrichment._helpers import relative_path, safe_read

if TYPE_CHECKING:
    from slopgate.context import HookContext


def _lookup_root(ctx: HookContext, current_path: Path | None) -> Path:
    roots = (ctx.config.repo_root, ctx.config.root)
    if current_path is not None:
        for root in roots:
            try:
                current_path.relative_to(root)
            except ValueError:
                continue
            return root
        return current_path.parent
    return ctx.config.repo_root


def find_local_call_sites(
    func_name: str,
    ctx: HookContext,
    current_path: Path,
    *,
    max_sites: int = 3,
) -> list[str]:
    """Return a few repo-local call-site citations for a wrapper function."""
    root = _lookup_root(ctx, current_path)
    needle = f"{func_name}("
    citations: list[str] = []
    for candidate in sorted(root.rglob("*.py")):
        try:
            rel_parts = candidate.relative_to(root).parts
        except ValueError:
            rel_parts = candidate.parts
        if candidate == current_path or any(part.startswith(".") for part in rel_parts):
            continue
        source = safe_read(candidate, max_bytes=64_000)
        if needle not in source:
            continue
        for lineno, line in enumerate(source.splitlines(), start=1):
            if needle not in line:
                continue
            snippet = line.strip()[:120]
            citations.append(f"{relative_path(candidate, root)}:{lineno}: `{snippet}`")
            break
        if len(citations) >= max_sites:
            break
    return citations


_LOGGER_NEEDLES = (
    "get_logger",
    "get_project_logger",
    "structlog.get_logger",
    "from loguru import logger",
    "logger =",
)


def _nearby_python_files(root: Path, current_path: Path | None) -> list[Path]:
    if current_path is None:
        return sorted(root.rglob("*.py"))
    try:
        current_path.relative_to(root)
    except ValueError:
        return sorted(root.rglob("*.py"))
    return sorted(current_path.parent.glob("*.py"))


def _line_has_logger_pattern(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    if "import logging" in stripped or "from logging import" in stripped:
        return False
    if any(needle in stripped for needle in _LOGGER_NEEDLES):
        return True
    return "logger" in stripped.lower() and (
        stripped.startswith("from ") or stripped.startswith("import ")
    )


def find_logger_citations(
    ctx: HookContext,
    current_path: Path | None,
    *,
    max_sites: int = 3,
) -> list[str]:
    """Return nearby project logger import/factory citations."""
    root = _lookup_root(ctx, current_path)
    citations: list[str] = []
    for candidate in _nearby_python_files(root, current_path):
        if candidate == current_path:
            continue
        source = safe_read(candidate, max_bytes=64_000)
        for lineno, line in enumerate(source.splitlines(), start=1):
            if not _line_has_logger_pattern(line):
                continue
            snippet = line.strip()[:120]
            citations.append(f"{relative_path(candidate, root)}:{lineno}: `{snippet}`")
            break
        if len(citations) >= max_sites:
            break
    return citations
