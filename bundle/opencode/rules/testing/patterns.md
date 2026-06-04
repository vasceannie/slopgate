
# Test Patterns

## Structure

- **AAA Pattern**: Arrange → Act → Assert — clearly separated sections
- **One concept per test**: Each test validates a single behavior; data variations use parametrization, not loops-with-asserts (PY-TEST-003)
- **Descriptive names**: `test_expired_token_returns_401` not `test_auth_3`

## Fixtures & State

- **Fixtures in conftest.py** only — never in individual test files (vibeforcer PY-TEST-004 blocks this)
- **Factory pattern** for complex test data — not raw dict construction
- **No shared mutable state** between tests

## Mocking

- `unittest.mock` (Py) or `vitest/jest` (TS) for external dependencies
- Mock at the boundary (API calls, DB), not internal functions
- Prefer real objects when feasible — mocks hide bugs

## Test Integrity

- Optimize for bug detection, not pass-rate. A regression test must satisfy the "would fail on the broken implementation" rule; name the production line, contract, or integration seam it protects.
- Assert behavior and contracts: rendered text, API responses, persisted state, emitted events, CLI output, database rows, or exact model fields. Presence checks (`is not None`, mounted, was called, `success is True`) are insufficient unless that is the actual contract.
- Mocks may replace true external boundaries only: network, filesystem when unavoidable, time, randomness, paid APIs, subprocesses, or slow third-party systems. Do not mock parsers, serializers, event handlers, state stores, projections, renderers, or in-process collaborators when the risk is their interaction.
- If a mock is necessary, assert the semantic payload or arguments passed through it. A mock without content assertions is only a smoke test.
- Use real constructors, factories, fixtures, sample wire payloads, or recorded protocol events. Avoid `cast()` bypasses, raw dicts, and partial fake objects unless testing malformed input handling.
- For multi-step pipelines, include at least one thin integration or contract test through the real path; stub only the true outer boundary.
- Bug-fix tests must fail before the fix, or explain why that is unsafe/impossible and add the closest lower-level check. Final notes must report behavior proved, mocks used and why, real path exercised, and verification command.

## TUI/Dataflow Regression Tests

- For TUI or dataflow bugs, do not stop at widget-level tests. Feed a realistic run/event payload through the production parser, enrichment, projection/store, event-handler path, and assert rendered or screen-facing state. Direct widget-prop injection is acceptable only when the upstream pipeline that produces those props also has coverage.

## Execution

- Run `pytest -n auto` (parallel) for suites >20 tests — install `pytest-xdist` if missing
- Prefer running single tests during development, full suite before commit

## Protected Quality Tests

- `QA-PATH-003`: do not edit `tests/quality/` to make hooks pass. Fix production/test code that violates the rule, or add normal project tests outside the quality harness.

## Coverage

- 100% on critical business logic, even if project target is lower
