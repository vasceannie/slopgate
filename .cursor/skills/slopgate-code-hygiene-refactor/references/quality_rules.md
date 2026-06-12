# Quality Rules Reference

This reference is intentionally Slopgate-oriented. Project-specific Makefile targets may exist, but the common cross-project gate is the repo-root Slopgate quality flow.

## Operational rules

- Do not edit quality tests, hook configs, thresholds, baselines, or allowlists just to pass.
- Public `slopgate lint check` is full-scope from the discovered repo root. Do not pass a path argument.
- Post-edit findings mean the mutation likely landed; fix the touched files before continuing.
- Prefer structural repairs over suppressions.

## Common runtime/hook rule IDs

### `PY-CODE-017` — flat sibling modules

- Trigger: third same-prefix sibling such as `foo_a.py`, `foo_b.py`, `foo_c.py`, or a `foo_*.py` file beside an existing `foo/__init__.py` package.
- Fix: convert to `foo/` package with cohesive siblings and a thin `__init__.py` facade.
- Verification: compile moved modules, run import/focused tests, rerun the hook or repo-root lint.

### `PY-CODE-018` — oversized Python module

- Trigger: projected or existing Python file exceeds module-size thresholds.
- Fix: split by responsibility; use package facade/re-exports to preserve public API.
- Verification: compile every split module, focused tests, repo-root lint.

### `QUALITY-LINT-001` — touched-file lint backstop

- Trigger: after a tool call, touched files have lint/quality findings such as oversized module, god class, long method, duplicate helper, fixture smell, repeated literal, or type-suppression issue.
- Fix: repair the landed mutation; do not continue unrelated work.
- Verification: focused tests first, then `cd <repo> && HOME=/home/trav /home/trav/.local/bin/slopgate lint check`.

### `PY-AST-001` — parse/read failure

- Trigger: Python file cannot be parsed/read.
- Fix: restore syntax before any further refactor.
- Verification: `python3 -m py_compile <file>`.

### `PY-CODE-012` / `PY-CODE-013` and smell-class findings

- Thin wrappers: inline or add real value.
- Feature envy: move behavior to the object/domain owner.
- Duplicate helpers/repeated literals: search for existing constants/helpers before adding new ones; when Slopgate cites an existing constant, import the symbol from the cited `path:line` instead of creating another name.
- Repeated literal camouflage: never split strings (`"pri" + "mary"`), stitch partial constants (`PK_PRI + "mary"`), or add aliases solely to bypass duplicate-literal detectors.
- Type suppression: load `type-strictness` and model the type correctly.

## Structural thresholds to assume unless project policy says otherwise

- Long method: about >50 lines or high complexity.
- God class: method-count or class-body-size signal; split collaborators by responsibility.
- Oversized module: soft around >350 lines, hard around >600 lines in common Slopgate policy.
- Test module/fixture bloat: keep tests focused; keep `conftest.py` as a thin wiring layer when fixture support modules are allowed.

## Safe verification ladder

1. Syntax: `python3 -m py_compile <changed.py>`.
2. Focused tests for touched behavior.
3. Type/lint commands native to the project.
4. Repo-root Slopgate gate:
   ```bash
   cd /path/to/repo && HOME=/home/trav /home/trav/.local/bin/slopgate lint check
   ```
5. Broader suite only after focused checks pass.
