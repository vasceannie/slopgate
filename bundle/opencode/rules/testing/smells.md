
# Test Smells to Avoid

Enforcer hooks block these at edit time. Write clean tests from the start.

## Assertion Roulette (PY-TEST-001)

Multiple assertions in one test without messages — when it fails, which one broke?

```python
# Bad — assertion roulette
def test_user():
    assert user.name == "Alice"
    assert user.age == 30
    assert user.active is True

# Good — one concept per test, or use messages
def test_user_name():
    assert user.name == "Alice"

def test_user_is_active():
    assert user.active is True
```

## Conditional Assertions (PY-TEST-002/003)

Logic in tests hides which path was actually tested:

```python
# Bad — conditional assertion
def test_response(response):
    if response.status == 200:
        assert response.data is not None
    else:
        assert response.error is not None

# Good — separate tests for each case
def test_success_response_has_data(success_response):
    assert success_response.data is not None

def test_error_response_has_error(error_response):
    assert error_response.error is not None
```

## Loops With Assertions

```python
# Bad — loop hides which iteration failed
for item in items:
    assert item.valid

# Good — parametrize
@pytest.mark.parametrize("item", items, ids=lambda i: i.name)
def test_item_valid(item):
    assert item.valid
```

## Sleep in Tests (PY-TEST-002)

`time.sleep()` makes tests slow and flaky. Use `unittest.mock.patch` to mock time, or `asyncio` test utilities for async code.

## Assertion-Free Tests

Every test must assert something. A test that only calls code without verifying results is not a test — it's a smoke check at best.

```python
# Bad — no assertion
def test_process_data(sample_data):
    process(sample_data)  # runs but proves nothing

# Good — verify the result
def test_process_data(sample_data):
    result = process(sample_data)
    assert result.status == "completed"
```

## Mock Theater

Mocks that replace the behavior under test make fragile code look correct.

```python
# Bad — verifies the mock, not the pipeline
handler = MagicMock(return_value={"company": "Acme"})
run_screen.apply_projection(handler())
handler.assert_called()

# Good — feeds realistic input through production code and checks output
projection = projection_store.apply(real_field_focused_event(company="Acme"))
run_screen.apply_projection(projection)
assert run_screen.current_company == "Acme"
```

- Do not mock parsers, serializers, event handlers, state stores, projections, renderers, or in-process collaborators when their interaction is the risk.
- If a mock is needed for a true boundary, assert payloads/arguments with semantic content; `assert_called()`, `called`, or call counts alone are too weak.

## Structural or Presence-Only Assertions

Tests that check shape without meaning miss real regressions.

```python
# Bad — data exists, but could be blank or wrong
assert summary.company is not None
assert result.success is True

# Good — asserts the contract that users rely on
assert summary.company == "Acme"
assert preview.stats.company_text == "Acme"
```

- Avoid `is not None`, mounted/rendered-only checks, bare truthiness, and `success is True` unless that exact presence/flag is the contract.
- Avoid raw dicts, `cast()` schema bypasses, and partial fakes when real models/factories/sample wire payloads are available.

## Leaf-Only Coverage for Pipeline Bugs

Widget/unit tests are useful but insufficient when the bug lives between layers.

- For TUI/dataflow failures, do not inject final widget props as the only coverage.
- Add a thin integration/contract test that runs realistic payloads through the production parser → enrichment → projection/store → handler path and checks rendered or screen-facing state.

## Eager Tests (Too Many Assertions)

A test that asserts 8+ things is testing too many behaviors at once. When it fails, you don't know which behavior broke.

- Split into focused tests, each covering one behavior
- If assertions are related (e.g., checking a single object), group them but add assertion messages

## Long Tests (>50 lines)

Long tests are hard to read and usually test too much. Split by Arrange/Act/Assert boundaries — each test should have one Act.
