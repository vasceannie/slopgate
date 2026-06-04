---
globs: **/test_*.py, **/*_test.py, **/tests/**/*.py, **/*.test.ts, **/*.test.tsx, **/*.spec.ts, **/*.spec.tsx
---

# Test Patterns

## Structure

- **AAA:** Arrange → Act → Assert, clearly separated.
- One concept per test; variations use parametrization, not loops-with-asserts (PY-TEST-003).
- Descriptive names: `test_expired_token_returns_401`, not `test_auth_3`.

## Fixtures

- Fixtures in `conftest.py` only — never in test files (PY-TEST-004).
- Factory pattern for complex data, not raw dicts.
- No shared mutable state between tests.

## Mocking

- `unittest.mock` (Py) / `vitest|jest` (TS) for external deps.
- Mock at the boundary (API/DB), not internal functions.
- Prefer real objects when feasible.

## Test integrity

- Optimize for bug detection, not pass-rate. Regression tests must satisfy the "fails on broken implementation" rule — name the production line/contract it protects.
- Assert behavior and contracts: rendered text, API responses, persisted state, emitted events, CLI output, exact model fields.
- Mocks only for true external boundaries: network, filesystem (when unavoidable), time, randomness, paid APIs, subprocesses. Not parsers/serializers/handlers/stores/projections/renderers.
- If a mock is necessary, assert semantic payload through it.
- Multi-step pipelines: at least one thin integration/contract test through the real path.
- Bug-fix tests must fail before the fix (or explain why infeasible + add closest lower-level check).
- Final notes: behavior proved, mocks + why, real path exercised, verification command.

## TUI/dataflow

For TUI/dataflow bugs, do not stop at widget-level tests. Feed a realistic run/event payload through the production parser → enrichment → projection/store → handler and assert rendered state. Widget-prop injection only when the upstream pipeline is also covered.

## Execution

- `pytest -n auto` (parallel) for >20 tests (`pytest-xdist`).
- Single tests during dev, full suite before commit.
- 100% on critical business logic.

## Protected paths

- `QA-PATH-003`: do not edit `tests/quality/` to make hooks pass. Fix the violation, or add normal tests outside the quality harness.
