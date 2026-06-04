# Python Testing Standards (subagent digest)
# Source of truth: ~/.claude/rules/testing/

## Structure
- AAA pattern: Arrange → Act → Assert, clearly separated
- One concept per test; descriptive names: `test_expired_token_returns_401`
- Fixtures exposed to tests belong in the narrowest `conftest.py`; support/fixture implementation modules are fine when imported and surfaced by that conftest
- Factory pattern for complex test data, not raw dict construction
- No shared mutable state between tests

## Smells to Avoid
- Assertion roulette: multiple asserts without messages — split or add messages
- Conditional assertions: `if x: assert y` — separate tests per case
- Loops with assertions: parametrize instead
- `time.sleep()` in tests: mock time or use async test utils
- Assertion-free tests: every test must assert something
- Eager tests (8+ assertions): split by behavior
- Long tests (>50 lines): split by Arrange/Act/Assert boundaries

## Test Integrity
- Optimize for bug detection, not pass-rate: every regression test must be able to explain how it would fail on the broken implementation.
- Assert behavior/contracts, not structure: rendered text, API responses, persisted state, emitted events, CLI output, database rows, or exact model fields.
- Avoid weak presence checks (`is not None`, mounted, was called, `success is True`) unless that is the actual contract.
- Mock only true external boundaries. Do not mock parsers, serializers, event handlers, state stores, projections, renderers, or in-process collaborators when the risk is their interaction.
- If a mock is necessary, assert semantic payloads/arguments, not just call count.
- Use real constructors, factories, fixtures, sample wire payloads, or recorded events. Avoid `cast()` bypasses, raw dicts, and partial fakes unless testing malformed input.
- For fragile pipelines, include one thin integration/contract test through the real path. For TUI/dataflow bugs, feed realistic run/event payload through parser → enrichment → projection/store → handler and assert rendered or screen-facing state.

## Fixtures
- Scope hierarchy: narrowest conftest that needs them
- Fixture implementations may live in dedicated support modules when the narrowest `conftest.py` imports/exposes them; tests should request fixtures by name, not import fixture functions directly
- Noun naming: `db_session`, `auth_client`, `sample_user`
- `yield` fixtures for setup/teardown; cleanup runs regardless of pass/fail
- Session/module scoped must be stateless or read-only
- Higher-scoped cannot depend on lower-scoped

## Marks
- `@pytest.mark.parametrize` with `ids=` for readability
- Register custom marks in `pyproject.toml` to avoid warnings
- `@pytest.mark.slow`, `@pytest.mark.integration` for categorization

## Execution
- `pytest -n auto` for suites >20 tests (parallel via pytest-xdist)
- Single tests during development, full suite before commit
- Config: `addopts = "-ra -q --strict-markers"`, `filterwarnings = ["error"]`

## Mocking
- Mock at the boundary (API, DB), not internal functions
- Prefer real objects when feasible — mocks hide bugs
