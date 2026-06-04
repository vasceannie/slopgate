# Python Standards (subagent digest)
# Source of truth: ~/.claude/rules/python/, quality-complexity.md, perf-awareness.md

## Style
- `from __future__ import annotations` in every new file
- Relative imports within packages: `from ._config import get_config`
- Google/NumPy docstrings, imperative voice
- `@dataclass(frozen=True)` for pure data containers
- `with` for all resource handling (files, sockets, DB connections)
- Modern syntax: `str | None` not `Optional[str]`, `list[str]` not `List[str]`
- Use the project logger/telemetry abstraction; active hooks may block direct stdlib `logging.getLogger()` in Python sources
- If a project still uses stdlib logging, use `%s` formatting in logger calls, not f-strings
- Activate `.venv` before execution; use `uv` or `poetry`, never global `pip`
- Run `ruff check` + `pyright` after every edit — zero regressions

## Not This
- `print()` for logging
- TODO/FIXME markers — fix it or track externally
- Commented-out code — remove entirely
- Hardcoded file paths — use `pathlib` / config
- Magic numbers — name constants
- Unreachable code after return/raise/break/continue
- Deprecated: `typing.List`, `typing.Dict`, `typing.Optional`, `os.path`

## Type Safety
- No `Any` — use `object`, `Protocol`, or narrow unions
- No `# type: ignore`, `# noqa`, `# pylint: disable`, `# pyright: ignore`, or `# ty: ignore`; fix the underlying type/lint cause
- No `cast()` without justification — narrow with isinstance or TypeGuard
- Use `Protocol` for structural typing, `TypeVar` for generics, `TypedDict` for dict shapes
- `Final` for constants; discriminated unions with `Literal` kind fields
- Narrow at point of use with guard clauses or isinstance

## Error Handling
- Domain-specific exceptions: `raise StorageTimeoutError("msg")` not generic Exception
- Always `raise ... from err` to chain and preserve traces
- Structured logging, not print; graceful degradation for non-critical failures
- No bare `except:`, no `except Exception: pass`, no `except Exception: return None`
- Define base exception per package, derive specifics from it

## Complexity Budgets
- Cyclomatic complexity ≤12/function; method ≤50 lines; params ≤4 (excl self/cls)
- Nesting ≤4 levels; class methods ≤15; class ≤400 lines; module ≤600 lines
- Line length ≤120 chars (trailing whitespace counts)
- Use guard clauses, named predicates, dataclass params, strategy pattern

## Architecture
- Single Responsibility per function/module; composition over inheritance
- Functional core / imperative shell; dependency injection over globals
- Don't extract helpers unless reused or genuinely complex
- Flat > nested: early returns and guard clauses before extraction
- Functions: verb phrases; classes: noun phrases; booleans: question form

## Performance
- dict/set lookups over list scans for membership; watch for hidden O(n²)
- Generators for large data; `yield` over building full lists
- `functools.lru_cache` for expensive pure functions
- Batch DB queries; use async for concurrent independent I/O
- Lazy imports for heavy packages used conditionally

## Security
- All user input is untrusted — validate with Pydantic
- Parameterized SQL only; validate file paths (no traversal); validate URLs (no SSRF)
- Secrets in env vars, never hardcoded; never log secrets
- `hmac.compare_digest` for token comparison; bcrypt/argon2 for passwords
