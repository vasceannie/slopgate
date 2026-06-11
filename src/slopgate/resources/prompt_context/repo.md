# Repository Rules (hook-enforced — violations are auto-blocked)

## Reading Files
- **Always read files in full first.** Never pass `offset` or `limit` on the first read of a file.
- Once you have read a file completely, subsequent partial reads are fine.
- Exempt: `.log`, `.csv`, `.txt`, and files over 200KB.

## Python Types
- Never use `Any` from typing. Use `Protocol`, `TypedDict`, `TypeVar`, or concrete types.
- Never add suppression comments: `# type: ignore`, `# ty: ignore`, `# noqa`, `# pyright: ignore`, `# pylint: disable`.
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
- Use `@pytest.mark.parametrize` for finite named examples, edge cases, and regressions; do not hide asserts inside `for` loops.
- Use Hypothesis for broad input domains and invariants such as round-trip, idempotence, monotonicity, bounds, stable ordering, parser/validator no-crash behavior, or malformed input handling. Do not add Hypothesis as a new dependency without checking project policy.
- Parametrization and Hypothesis can coexist: explicit examples document known behavior; property tests explore the general invariant.
- Put shared fixtures through the nearest `conftest.py`. Keep `conftest.py` as a thin registry when fixtures are large; implementation-heavy fixtures may live in `tests/<area>/_fixtures/` or `tests/<area>/support/`. Use fixtures by name in test signatures or pytest decorators; do not import them from `conftest.py`.
- No `time.sleep()` in tests. No `try/except` wrapping test logic.
- Every `assert` needs a descriptive message (3+ bare asserts in a row = blocked).

## Protected Paths (read-only unless explicitly approved)
- `Makefile`, `Dockerfile`, `docker-compose.yml`
- `.claude/hooks/*`, `.claude/hook-layer/config.json`
- Linter configs: `pytest.ini`, `.eslintrc*`, `.flake8`, `.pylintrc`, `ruff.toml`, `pyrightconfig*`, `biome.json`
- Quality tests: `src/test/code-quality.test.ts`, `tests/quality/`
- Staging hook-rule authoring surfaces: `src/slopgate/rules/python_ast/_staging/`

## Code Quality
- No `TODO`, `FIXME`, `HACK`, `XXX` markers — track work in issues.
- No `import logging` / `from logging import` — use the project logger.
- No hardcoded absolute paths (`/home/user/...`, `/Users/...`).
- No magic numbers — define named constants.
- No non-standard Python import aliases. Use canonical library aliases only (`pandas as pd`, `polars as pl`, `numpy as np`, `matplotlib.pyplot as plt`); do not rename imports to hide duplicate code.
- No stacked private module chains like `pkg._impl._core` or `from src.cli.auth._orchestrate._core import X`. One private segment is allowed; nested private segments mean the package needs a public facade or descriptive child modules.
- No commented-out code blocks.
- Functions: ≤50 lines, ≤4 params, nesting ≤4 levels, complexity ≤10.
- Classes: ≤10 non-dunder methods.

## Shell Commands
- No `set +e`, `2>/dev/null`, `|| true`, `|| :` — handle errors explicitly.
- No editing Python files via `sed -i`, `tee`, or `>` redirects — use Write/Edit tools.

## Hot Hook Preflight
- `PY-CODE-013`: do not add pass-through wrappers. Inline unless the wrapper validates/normalizes inputs, names a real domain boundary, centralizes policy/caching/permission/logging, adapts one interface to another, or hides unstable third-party API details.
- `PY-CODE-009`: group parameters by semantic meaning. In tests, prefer a named `Case` dataclass or builder defaults; do not make helpers that simply forward every arg to a constructor.
- `PY-CODE-018`: oversized modules need a cohesive split before more behavior. Prefer `module/` packages with `__init__.py` re-export facades, not line shaving or flat sibling sprawl.
- `PY-LOG-002`: event publishers/handlers and package-boundary adapters/clients/gateways must log with the project logger/telemetry abstraction before crossing the boundary; include event/service/correlation fields, never raw secrets/payloads.
- `PY-IMPORT-002`: use canonical aliases only (`np`, `pd`, project-established shorthands). Do not invent aliases to dodge duplicate-code or long-import findings.
- `QUALITY-LINT-001`: PostToolUse means the edit may already exist. Reread the touched file, fix only the reported collector/hit, and verify with the smallest repo-root quality command before continuing feature work.
- `SHELL-001`: do not hide failures with `2>/dev/null`, `set +e`, `|| true`, or `|| :`; rerun unsuppressed or capture stderr explicitly.
- `ERRORS-BASH-001` / `ERRORS-FAIL-001`: treat error output or non-zero exits as active repair work. Inspect stdout/stderr, fix the smallest failing command, then rerun it.
- `PY-CODE-012` and `PY-IMPORT-001` are context-only advisory signals. Do not retry solely for those unless the boundary is already in scope.

## Baselines (`baselines.json`)
- **Mental model:** baseline is an **inventory of known debt** captured at enrollment — a map of what to fix, not a waiver. `slopgate lint` only **blocks NEW** violations; listed stable IDs are still real defects.
- **When you touch a file:** read matching baseline entries for that path (Read/Grep `baselines.json` or run `slopgate lint check --details`). Prefer fixing baselined hits in files you are already editing before adding behavior nearby.
- **After you fix code:** run `slopgate lint check` — it prunes stale `stable_id` entries automatically. On a clean pass it mirrors the current scan into the baseline file.
- **Do not:** treat "baselined" / "known debt" as acceptable; skip fixes because lint exited 0; run `slopgate lint baseline`, `quality-gate baseline`, or `vfc lint baseline`; or bulk re-freeze to hide regressions (`slopgate lint freeze` is one-time init only). Never hand-edit the baseline to add NEW violation ids — hooks deny inflation (`BASELINE-001`).
- **Optional triage:** the `code-hygiene-refactor` skill's `analyze_violations.py --baselines baselines.json` groups hits by rule/file for repair planning.

## Before Stopping
- Run `make quality` or the project quality command.
- Do not dismiss issues as "pre-existing" or "baselined" — fix them, shrink the baseline, or flag explicitly for the user.

## Module Organization
- When splitting a large module into smaller files, **create a sub-package** (directory with `__init__.py`), not flat `_prefix_*.py` sibling files.
- Example: splitting `executor.py` into concerns → create `executor/` package with `__init__.py`, `fill.py`, `routing.py`, `types.py`, etc.
- The `__init__.py` should re-export the public API so external imports don't change.
- Never create 3+ files with a shared `_prefix_` in the same directory.
