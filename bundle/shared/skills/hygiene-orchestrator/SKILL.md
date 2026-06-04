---
name: hygiene-orchestrator
description: |
  Coordinate multi-file or repo-wide hygiene repairs after Slopgate, type, lint, or test-quality failures. Use when code-hygiene-refactor is not enough: multiple files share findings, package splits affect public imports, QUALITY-LINT-001 repeats across a repo, or parallel repair batches are needed. Preserves guardrails; never rebaselines or weakens rules without explicit approval.
---

# Hygiene Orchestrator

Use this skill for broad quality cleanup. For one file or one local hook denial, start with `code-hygiene-refactor`; escalate here when the work needs batching, dependency ordering, or multiple agents.

## Non-negotiables

1. **Do not weaken quality gates**: no threshold/allowlist/baseline/test edits unless Trav explicitly approves that policy change.
2. **No overlapping edits**: two agents/batches must not write the same file or package facade at the same time.
3. **Structural repairs before lint churn**: package splits, public API preservation, and import graph cleanup are coordination tasks, not parallel free-for-alls.
4. **Repo-root quality checks**: run public Slopgate lint from the repo root with no path arguments.
5. **Record progress durably** when context may compact: issue manifest, batch ownership, completed files, validation results, blockers.

## Intake workflow

1. Capture the current signal:
   - hook rule IDs (`PY-CODE-017`, `PY-CODE-018`, `QUALITY-LINT-001`, etc.);
   - linter/type/test commands and outputs;
   - affected paths and import owners.
2. Classify findings:
   - package/architecture (`PY-CODE-017`, oversized modules, god classes);
   - type safety (`type-strictness` needed);
   - test quality (`test-extender` likely needed);
   - duplicate helpers/constants;
   - operational hook/runtime failures.
3. Decide whether work is serial or parallel.

## Batching strategy

### Serial-only classes

Run these as one coordinated batch, not parallel edits:

- module-to-package splits that touch `__init__.py` facades;
- flat sibling package conversions (`PY-CODE-017`);
- public API/import migrations;
- shared type/protocol changes;
- shared constants/helper ownership changes.

### Parallel-safe classes

May be split into non-overlapping file batches after import ownership is clear:

- independent test assertion/message fixes;
- dead code removal in unrelated directories;
- local type narrowing that does not alter shared signatures;
- repeated small smells in unrelated packages.

### Ownership rule

A batch owns:

- exact files it may edit;
- package facades it may touch;
- tests it must run;
- imports it may update.

No other batch can touch those paths until validation completes.

## Suggested repair waves

1. **Wave 0: stop the bleeding**
   - Restore parseability (`PY-AST-001`) and failing imports.
   - Revert or repair landed PostToolUse bad mutations.
2. **Wave 1: architecture/package shape**
   - Convert flat sibling clusters to packages.
   - Split oversized modules/god classes into cohesive owners.
   - Preserve public API with facades and tests.
3. **Wave 2: shared types/constants/helpers**
   - Add protocols/TypedDicts/parameter objects.
   - Consolidate duplicate helpers/constants.
4. **Wave 3: localized lint/test cleanup**
   - Dispatch parallel file-owned batches.
5. **Wave 4: verification and drift check**
   - Focused tests, type/lint, repo-root Slopgate, broader suite as needed.

## Agent handoff template

```text
Batch: <name>
Rule IDs: <ids>
Owned files: <files>
Do not touch: <shared facades/files owned by other batches>
Required skills: code-hygiene-refactor, type-strictness/test-extender if relevant
Goal: <specific repair>
Public API/imports to preserve: <imports>
Verification: <commands>
Return: summary, files changed, validation output, blockers
```

## Verification ladder

```bash
# Syntax for changed Python files
python3 -m py_compile <changed files>

# Focused tests by touched behavior
python3 -m pytest <focused tests> -q

# Repo-root Slopgate gate; no path args
cd /path/to/repo && HOME=/home/trav /home/trav/.local/bin/slopgate lint check
```

For Slopgate source changes:

```bash
cd /home/trav/.openclaw/workspace-hooker/slopgate
.venv/bin/python -m pytest tests/test_flat_file_sibling_packages.py tests/test_size_guard_hook_behavior.py -q
HOME=/home/trav .venv/bin/slopgate test
git diff --check
```

## Progress record shape

Keep this in a project scratch file such as `.hygiene/tracking.json`, `.hermes/hygiene-progress.md`, or the session todo list when local files are not appropriate:

```json
{
  "session": "ISO-8601 timestamp",
  "goal": "repo quality repair",
  "initial_signal": {"rules": [], "commands": []},
  "batches": [
    {"name": "package-split", "owned_files": [], "status": "pending", "validation": []}
  ],
  "completed_files": [],
  "blocked": []
}
```

Use `.hygiene/` unless the project already has `.hygeine/`; do not create both spellings in the same repo.

## Related skills

- `code-hygiene-refactor` for single-denial repair tactics.
- `type-strictness` for type-safety failures.
- `test-extender` for test additions/repairs.
- `code-smell-utility-locator` if available for helper/constant radar before consolidating utilities.
