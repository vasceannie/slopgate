---
globs: **/*.py
---

# Python Style

## Environment

- Activate `.venv/bin/activate` first. Deps: `uv` or `poetry`, never global `pip`.
- After edits: `ruff` (lint + format) + `pyright`/`mypy`.

## Style

- `from __future__ import annotations` in new files.
- Python 3.10+ syntax: `str | None`, `list[str]`. No `typing.List`/`Dict`/`Optional`/`Union`.
- `@dataclass(frozen=True)` for pure data. `with` for resources. `asyncio` (or `AnyIO` cross-backend).
- Docstrings: Google or NumPy, imperative.
- `pathlib.Path`, not `os.path`.

## Logging

- `logger = logging.getLogger(__name__)` — never hardcode name.
- Use `%s` formatting (`logger.info("Processing %s", id)`) — avoids string construction when disabled.
- Prefer `structlog` or project standard.

## Banned (slopgate)

- `print()` for logging (PY-LOG-001)
- TODO/FIXME (PY-QUALITY-007)
- Commented-out code (PY-QUALITY-008)
- Hardcoded paths (PY-QUALITY-009)
- Magic numbers (PY-QUALITY-010)
- Unreachable code after `return`/`raise`/`break`/`continue` (PY-CODE-016)
