
# Test Smells to Avoid

Enforcer hooks block these patterns at edit time. Keep each test focused and
make failures identify the behavior that broke.

## Assertion Roulette (PY-TEST-001)

Three or more consecutive bare `assert` statements are blocked. Add a
descriptive message to each assertion or split unrelated behaviors into
focused tests:

```python
def test_user_fields():
    assert user.name == "Alice", "the user name should be Alice"
    assert user.age == 30, "the user age should be 30"
    assert user.active is True, "the user should be active"
```

## General Test Smells (PY-TEST-002)

The hook blocks `time.sleep()`, broad `try/except` blocks, skip markers without
reasons, and unittest-style assertion methods. Use deterministic waits,
`pytest.raises(...)`, a stated skip reason, and plain assertions with messages.

## Loop Assertions (PY-TEST-003)

The hook blocks `for` or `while` bodies that contain assertions. For a finite
named set of cases, use parametrization with readable IDs:

```python
@pytest.mark.parametrize(
    "item",
    [pytest.param(item, id=item.name) for item in items],
)
def test_item_is_valid(item):
    assert item.valid, f"{item.name} should be valid"
```

Use Hypothesis for broad invariants such as round trips, idempotence, bounds,
stable ordering, malformed-input handling, or no-crash behavior.

## Fixtures Outside conftest.py (PY-TEST-004)

Define shared pytest fixtures in the nearest `conftest.py`; keep heavy fixture
implementation in the area's support module when needed. Tests request the
fixture by name rather than importing it:

```python
# tests/engine/conftest.py
@pytest.fixture
def client():
    return TestClient(app)
```

## Conditional Assertions (batch lint: conditional-assertion)

The batch lint detector reports assertions nested under runtime branches.
Split each branch into a focused test so every case has a deterministic
assertion path. This is distinct from the hook's `PY-TEST-003`, which targets
assertions directly inside loops.

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
