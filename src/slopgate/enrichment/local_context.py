"""Small repo-local lookup helpers for enrichment messages."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from vibeforcer.enrichment._helpers import relative_path, safe_read

if TYPE_CHECKING:
    from vibeforcer.context import HookContext


def find_local_call_sites(
    func_name: str,
    ctx: HookContext,
    current_path: Path,
    *,
    max_sites: int = 3,
) -> list[str]:
    """Return a few repo-local call-site citations for a wrapper function."""
    root = ctx.config.root
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
