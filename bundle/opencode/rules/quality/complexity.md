# Complexity Budgets

These thresholds are enforced by hooks (AST rules) and vibeforcer lint. Stay within them by design.

## Thresholds

| Metric | Limit | What To Do When Close |
|---|---|---|
| Cyclomatic complexity | ≤12 per function (PY-CODE-015) | Extract conditional branches into named predicates |
| Method length | ≤50 lines (PY-CODE-008) | Split into setup → core logic → cleanup |
| Parameter count | ≤4 excluding self/cls (PY-CODE-009) | Use a config dataclass or builder pattern |
| Nesting depth | ≤4 levels (PY-CODE-011) | Guard clauses, early returns, extract inner loops |
| Class methods | ≤15 per class (PY-CODE-014) | Split into composed services |
| Class lines | ≤400 | Extract domain logic into separate modules |
| Module lines | ≤600 hard / ≤350 soft (QUALITY-LINT-001 / PY-CODE-018) | Split by responsibility boundary |

## Patterns That Stay Under Budget

- **Guard clauses** reduce nesting by 1-2 levels each
- **Named predicates** (`is_valid_input()`) reduce cyclomatic complexity while keeping readability
- **Dataclass params** collapse 6 parameters into 1 without losing type safety
- **Strategy pattern** replaces long if/elif chains with dispatch dictionaries

## Why

These exact thresholds match the vibeforcer (PY-CODE-008/009, nesting/complexity AST rules) and vibeforcer lint detectors. Writing within budget means zero enforcement friction.

## Pre-write Scout

Before editing Python or tests, spend one minute checking:
- Target file length and role: if near ~250 module lines, ~40 function lines, 8 class methods, or 4 params, split first.
- Nearest sibling/test pattern: reuse the existing package, helper, fixture, or service shape instead of inventing another wrapper.
- Public API/import shape: avoid stacked private paths/imports like `pkg._impl._core` (`PY-IMPORT-003`).
- Likely hot hooks: `PY-CODE-013`, `PY-CODE-017`, `PY-CODE-018`, `QUALITY-LINT-001`, `PY-QUALITY-009`, `PY-QUALITY-010`, `PY-LOG-002`.

## Line Width

- **≤120 characters per line** (vibeforcer PY-CODE-010, vibeforcer lint `long-line`)
- Excludes: docstrings, comment-only lines, URLs, import statements
- Trailing whitespace counts toward length (consistent with ruff/flake8 E501)
- If a line is too long: break arguments across lines, extract variables, or use intermediate results

## Repair After a Complexity Hook

- `QUALITY-LINT-001` is the touched-file lint backstop. Do not continue feature work until the touched file is clean.
- First move: reread the target file and extract the smallest cohesive helper/service/package slice. Avoid full-file rewrites.
- For `PY-CODE-018` module-size findings, split into a sub-package with `__init__.py` re-exporting the public API; do not create flat `_prefix_*.py` sibling sprawl (`PY-CODE-017`).
- `PY-QUALITY-009`: route filesystem paths through config/pathlib/project constants; do not turn URL routes into fake path constants.
- `PY-QUALITY-010`: name semantic constants before replacing repeated literals; avoid readability hacks.
- Verification: use syntax/focused tests for touched files first; for Vibeforcer lint use repo-root/full-scope only: `cd <repo-root> && vibeforcer lint check`.
