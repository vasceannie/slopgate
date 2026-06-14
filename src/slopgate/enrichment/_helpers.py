"""Shared helpers for enrichment package internals.

These helpers intentionally keep failures silent (best effort) to avoid
breaking the hook pipeline.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from slopgate.constants import ENRICHMENT_MAX_READ_BYTES, METADATA_PATH

if TYPE_CHECKING:
    from slopgate.context import HookContext
    from slopgate.models import RuleFinding


_ast_parse_count = 0


def append_enrichment_message(finding: "RuleFinding", lines: list[str]) -> None:
    """Append enrichment lines to a finding message."""
    if not lines:
        return
    base_message = finding.message or ""
    finding.message = base_message.rstrip() + "\n" + "\n".join(lines)


def first_target_content(ctx: "HookContext") -> str:
    """Return the content of the first target, if available."""
    for target in ctx.content_targets:
        return target.content
    return ""


def safe_read(path: Path, max_bytes: int = ENRICHMENT_MAX_READ_BYTES) -> str:
    """Read a file, returning empty string on any error."""
    try:
        if path.stat().st_size > max_bytes:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def safe_parse(source: str) -> ast.Module | None:
    """Parse Python source, returning ``None`` on syntax errors."""
    global _ast_parse_count
    _ast_parse_count += 1
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def reset_parse_count() -> None:
    """Reset the package-level AST parse counter."""
    global _ast_parse_count
    _ast_parse_count = 0


def get_parse_count() -> int:
    """Return the number of ``_safe_parse`` calls since the last reset."""
    return _ast_parse_count


def resolve_path(path_str: str, root: Path) -> Path:
    """Resolve a possibly-relative path against ``root``."""
    path = Path(path_str)
    if path.is_absolute():
        return path
    return (root / path).resolve()


def relative_path(path: Path, root: Path) -> str:
    """Return a path relative to root when possible."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def metadata_str(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None


def loaded_source_at_path(path_str: str, root: Path) -> tuple[Path, str] | None:
    full_path = resolve_path(path_str, root)
    source = safe_read(full_path)
    if not source:
        return None
    return full_path, source


def path_source_from_metadata(
    finding: RuleFinding, ctx: HookContext
) -> tuple[Path, str] | None:
    path_str = metadata_str(finding.metadata, METADATA_PATH)
    if path_str is None:
        return None
    return loaded_source_at_path(path_str, ctx.config.root)
