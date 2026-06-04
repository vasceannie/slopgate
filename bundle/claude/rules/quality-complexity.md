# Complexity Budgets

Enforced by hooks and slopgate lint.

| Metric | Limit | Hook | Fix |
|---|---|---|---|
| Cyclomatic complexity | ≤12/fn | PY-CODE-015 | Extract branches to named predicates |
| Method length | ≤50 lines | PY-CODE-008 | Setup → core → cleanup split |
| Parameters | ≤4 (excl self/cls) | PY-CODE-009 | Config dataclass or builder |
| Nesting depth | ≤4 | PY-CODE-011 | Guard clauses, early returns |
| Class methods (non-dunder) | ≤10 | PY-CODE-014 | Extract collaborator at 8 |
| Class lines | ≤400 | — | Extract to separate modules |
| Module lines | ≤350 soft / ≤600 hard | PY-CODE-018 / QUALITY-LINT-001 | Split by responsibility |
| Line width | ≤120 (excl docstrings/URLs/imports) | PY-CODE-010 | Break args, extract vars |

## Patterns that stay under budget

- Guard clauses → -1-2 nesting per use.
- Named predicates (`is_valid_input()`) reduce complexity readably.
- Dataclass params collapse 6 args into 1.
- Strategy/dispatch dict replaces long if/elif chains.

## Pre-write scout (before the hook fires)

Before editing Python or tests, spend one minute checking:
- Target file length and role: if near ~250 module lines, ~40 function lines, 8 class methods, or 4 params, split first.
- Nearest sibling/test pattern: reuse the existing package, helper, fixture, or service shape instead of inventing another wrapper.
- Public API/import shape: avoid stacked private paths/imports like `pkg._impl._core` (`PY-IMPORT-003`).
- Likely hot hooks: `PY-CODE-013`, `PY-CODE-017`, `PY-CODE-018`, `QUALITY-LINT-001`, `PY-QUALITY-009`, `PY-QUALITY-010`, `PY-LOG-002`.

## Preemptive splits

- Class at 8 methods, edit adds 9th/10th → extract collaborator now. Group by data mutated or collaborator called.
- Class at ~250 lines with visible sub-responsibilities → start extraction even if method count is fine.
- Function at ~40 lines, complexity ~9, or 4 params with 5th coming → extract the seam.
- Module at ~250 lines and growing → promote to package (see `python/project-structure.md`).

If the only way new code "fits" is stripping docstrings, removing `# why` comments, or collapsing try/except — the budget is telling you to split, not compress.

## Repair

- `QUALITY-LINT-001` is the touched-file backstop. Clean the touched file before resuming feature work.
- Reread the file; extract the smallest cohesive helper/service/package slice. No full-file rewrites.
- `PY-CODE-018` → sub-package with `__init__.py` re-exporting public API. Not flat `_prefix_*.py` sprawl (`PY-CODE-017`).
- `PY-CODE-014` god-class → extract collaborators by responsibility (data + collaborators), not random shuffling.
- `PY-QUALITY-009`: route filesystem paths through config/pathlib/project constants; do not turn URL routes into fake path constants.
- `PY-QUALITY-010`: name semantic constants before replacing repeated literals; avoid readability hacks.
- Verification: use syntax/focused tests for touched files first; for Slopgate lint use repo-root/full-scope only: `cd <repo-root> && slopgate lint check`.
