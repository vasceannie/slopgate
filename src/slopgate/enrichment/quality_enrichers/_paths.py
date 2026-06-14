"""Hardcoded path enrichment helpers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from slopgate.enrichment._helpers import (
    append_enrichment_message,
    relative_path,
    safe_read,
)

if TYPE_CHECKING:
    from slopgate.context import HookContext
    from slopgate.models import RuleFinding

_PATH_HINT_FILES = (
    "config.py",
    "settings.py",
    "paths.py",
    "constants.py",
    "env.py",
)
_PATH_HINT_TOKENS = ("PATH", "DIR", "ROOT", "BASE_PATH", "DATA_DIR")


def _path_hint_lines(content: str, max_lines: int = 4) -> list[str]:
    lines: list[str] = []
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if any(token in stripped for token in _PATH_HINT_TOKENS):
            lines.append(stripped)
            if len(lines) >= max_lines:
                break
    return lines


def _iter_path_config_candidates(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for base_dir in (root / "src", root / "app", root / "config", root):
        for name in _PATH_HINT_FILES:
            candidate = base_dir / name
            if candidate.exists():
                candidates.append(candidate)
    return candidates


def enrich_hardcoded_paths(finding: RuleFinding, ctx: HookContext) -> None:
    """Enrich PY-QUALITY-009 with central path-config hints."""

    extras: list[str] = []
    for candidate in _iter_path_config_candidates(ctx.config.root):
        content = safe_read(candidate, max_bytes=10_000)
        if not content:
            continue
        lines = _path_hint_lines(content)
        if not lines:
            continue

        relative = relative_path(candidate, ctx.config.root)
        extras.append(f"\nPath configuration found in `{relative}`:")
        extras.extend(f"  {line}" for line in lines)
        break

    if not extras:
        extras.append(
            "\nNo central path config found. Consider defining paths in a config module "
            + "or using environment variables."
        )

    append_enrichment_message(finding, extras)
