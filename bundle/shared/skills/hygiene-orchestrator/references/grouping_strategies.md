# Grouping Strategies for Hygiene Orchestration

## Golden rule

Two concurrent agents must never write the same file, package facade, shared helper, public type, or import migration surface.

## Strategy 1: serial architecture wave

Use first for:

- `PY-CODE-017` flat sibling package conversions;
- `PY-CODE-018` oversized module splits;
- god class extraction;
- shared public API/import migrations.

Why: these changes touch many imports and facades, so parallel edits create conflicts and broken transitional states.

## Strategy 2: file-owned parallel batches

Use after architecture is stable. Each batch owns a disjoint file set and focused tests.

Good for:

- assertion messages;
- local type narrowing;
- dead code cleanup;
- independent small smell fixes.

## Strategy 3: dependency-ordered batches

Order by dependency direction:

1. protocols/types/entities;
2. base classes/interfaces;
3. shared helpers/constants;
4. domain services/adapters;
5. entrypoints;
6. tests.

Run upstream/shared surfaces before consumers.

## Strategy 4: category specialists

Use category specialists only after file ownership is established:

- type safety -> `type-strictness`;
- structural smells -> `code-hygiene-refactor`;
- tests -> `test-extender`;
- duplicate helpers/constants -> helper/utility radar first.

## Batch prompt checklist

- Rule IDs and exact findings.
- Owned files.
- Files/facades not to touch.
- Public imports to preserve.
- Verification commands.
- Required return format: changed files, validation, blockers.
