# Repository Rules (hook-enforced — violations are auto-blocked)

## Reading Files
- **Always read files in full first.** Never pass `offset` or `limit` on the first read of a file.
- Once you have read a file completely, subsequent partial reads are fine.
- Exempt: `.log`, `.csv`, `.txt`, and files over 200KB.

## Python Types
- Never use `Any` from typing. Use `Protocol`, `TypedDict`, `TypeVar`, or concrete types.
- Never add suppression comments: `# type: ignore`, `# noqa`, `# pyright: ignore`, `# pylint: disable`.
- Fix the root cause instead of suppressing.

## Exception Handling
- Never write `except Exception: pass` or `except Exception: return None`.
- Catch **specific** exceptions (`ValueError`, `KeyError`, etc.).
- Broad `except Exception` must re-raise or log **and** propagate.

## Git
- Never use `--no-verify`, `-n`, or `core.hookspath` overrides.
- Never use `git stash && cmd && git stash pop` patterns.
- Fix whatever the hooks flag instead of bypassing them.

## Tests
- Use `@pytest.mark.parametrize` for data-driven tests, not `for` loops with `assert`.
- Put shared fixtures through the nearest `conftest.py`. Keep `conftest.py` as a thin registry when fixtures are large; implementation-heavy fixtures may live in `tests/<area>/_fixtures/` or `tests/<area>/support/`. Use fixtures by name in test signatures or pytest decorators; do not import them from `conftest.py`.
- No `time.sleep()` in tests. No `try/except` wrapping test logic.
- Every `assert` needs a descriptive message (3+ bare asserts in a row = blocked).

## Protected Paths (read-only unless explicitly approved)
- `Makefile`, `Dockerfile`, `docker-compose.yml`
- `.claude/hooks/*`, `.claude/hook-layer/config.json`
- Linter configs: `.eslintrc*`, `.flake8`, `.pylintrc`, `ruff.toml`, `pyrightconfig*`, `biome.json`
- Quality tests: `src/test/code-quality.test.ts`, `tests/quality/`
- Staging hook-rule authoring surfaces: `src/vibeforcer/rules/python_ast/_staging/`

## Code Quality
- No `TODO`, `FIXME`, `HACK`, `XXX` markers — track work in issues.
- No `import logging` / `from logging import` — use the project logger.
- No hardcoded absolute paths (`/home/user/...`, `/Users/...`).
- No magic numbers — define named constants.
- No commented-out code blocks.
- Functions: ≤50 lines, ≤4 params, nesting ≤4 levels, complexity ≤10.
- Classes: ≤10 non-dunder methods.

## Shell Commands
- No `set +e`, `2>/dev/null`, `|| true`, `|| :` — handle errors explicitly.
- No editing Python files via `sed -i`, `tee`, or `>` redirects — use Write/Edit tools.

## Hot Hook Preflight
- `PY-CODE-013`: do not add pass-through wrappers. Inline unless the wrapper validates/normalizes inputs, names a real domain boundary, centralizes policy/caching/permission/logging, adapts one interface to another, or hides unstable third-party API details.
- `PY-CODE-009`: group parameters by semantic meaning. In tests, prefer a named `Case` dataclass or builder defaults; do not make helpers that simply forward every arg to a constructor.
- `QUALITY-LINT-001`: PostToolUse means the edit may already exist. Reread the touched file, fix only the reported collector/hit, and verify with the smallest repo-root quality command before continuing feature work.
- `PY-CODE-012` and `PY-IMPORT-001` are context-only advisory signals. Do not retry solely for those unless the boundary is already in scope.

## Baselines
- `baselines.json` violations must only decrease, never increase.
- Do not run `quality-gate baseline .`, `vibeforcer lint baseline .`, or `vfc lint baseline .` to re-baseline away violations.

## Before Stopping
- Run `make quality` or the project quality command.
- Do not dismiss issues as "pre-existing" — fix them or flag explicitly.

## Module Organization
- When splitting a large module into smaller files, **create a sub-package** (directory with `__init__.py`), not flat `_prefix_*.py` sibling files.
- Example: splitting `executor.py` into concerns → create `executor/` package with `__init__.py`, `fill.py`, `routing.py`, `types.py`, etc.
- The `__init__.py` should re-export the public API so external imports don't change.
- Never create 3+ files with a shared `_prefix_` in the same directory.
