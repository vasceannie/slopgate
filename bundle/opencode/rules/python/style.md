
# Python Style & Conventions

## Environment

- Detect and activate `.venv/bin/activate` before execution
- **Dependencies**: `uv` or `poetry` — never global `pip`
- **Formatting**: `ruff` for lint + format, `pyright` or `mypy` for types — run both after edits

## Code Style

- **Docstrings**: Google or NumPy style, imperative voice
- **Data classes**: `@dataclass(frozen=True)` for pure data containers
- **Context managers**: `with` statements for all resource handling (files, sockets, DB)
- **Async**: `asyncio` for I/O-bound; `AnyIO` if cross-backend needed
- **Modern syntax**: Python 3.10+ unions (`str | None`), generic collections (`list[str]`)
- **`from __future__ import annotations`** in all new files

## Not This

- `print()` for logging — use structured loggers (vibeforcer PY-LOG-001)
- TODO/FIXME markers — fix it or track externally (vibeforcer PY-QUALITY-007)
- Commented-out code — remove entirely (vibeforcer PY-QUALITY-008)
- Hardcoded file paths — use `pathlib` / config (vibeforcer PY-QUALITY-009)
- Magic numbers — name constants (vibeforcer PY-QUALITY-010)

## Dead Code

- No unreachable code after `return`, `raise`, `break`, `continue` (vibeforcer PY-CODE-016)
- No deprecated stdlib patterns — use modern equivalents:
  - `typing.List` → `list`, `typing.Dict` → `dict`, `typing.Optional[X]` → `X | None`
  - `typing.Union[X, Y]` → `X | Y` (Python 3.10+)
  - `os.path` → `pathlib.Path`

## Logging

- Create loggers with `logging.getLogger(__name__)` — never hardcode a logger name
- Use `structlog` or project-standard structured logger when available
- Log format: `logger.info("action description", key=value)` — not f-string interpolation in log calls
- Use `%s` formatting in stdlib logger: `logger.info("Processing %s", item_id)` — avoids string construction when log level is disabled
