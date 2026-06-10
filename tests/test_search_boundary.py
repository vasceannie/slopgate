from __future__ import annotations

import re
from pathlib import Path

_FORBIDDEN_CORE_IMPORT = re.compile(
    r"slopgate\.(rules|engine|enrichment|lint)\b"
)


def _search_boundary_output() -> str:
    search_root = Path(__file__).resolve().parents[1] / "src" / "slopgate" / "search"
    matches: list[str] = []
    for path in sorted(search_root.rglob("*.py")):
        for line_no, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if _FORBIDDEN_CORE_IMPORT.search(line):
                rel = path.relative_to(search_root)
                matches.append(f"{rel}:{line_no}:{line}")
    return "\n".join(matches)


def test_search_imports_no_core_modules() -> None:
    """search/ must not import rules, engine, enrichment, or lint modules."""
    output = _search_boundary_output()
    assert output == "", f"search package imported forbidden core modules:\n{output}"
