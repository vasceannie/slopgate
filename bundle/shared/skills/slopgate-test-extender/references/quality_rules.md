# Test Quality Rules Reference

Rules for writing high-quality, maintainable pytest tests.

## Table of Contents

1. [Anti-Patterns](#anti-patterns)
2. [Assertion Requirements](#assertion-requirements)
3. [Magic Value Prevention](#magic-value-prevention)
4. [Fixture Guidelines](#fixture-guidelines)
5. [Test Naming Convention](#test-naming-convention)
6. [Test Classification](#test-classification)

---

## Anti-Patterns

### No Loops in Tests

```python
# BAD - loop in test
def test_validate_items():
    items = [1, 2, 3, 4, 5]
    for item in items:
        assert validate(item), f"Failed for {item}"

# GOOD - parametrized
@pytest.mark.parametrize("item", [1, 2, 3, 4, 5])
def test_validate_item(item: int) -> None:
    result = validate(item)
    assert result, f"Expected validate({item}) to return True"
```

### No Conditionals in Tests

```python
# BAD - conditional logic
def test_process_data(data):
    if data.type == "A":
        assert process(data) == expected_a
    else:
        assert process(data) == expected_b

# GOOD - separate tests or parametrize
@pytest.mark.parametrize(
    ("data_type", "expected"),
    [
        pytest.param("A", "result_a", id="type_a_processing"),
        pytest.param("B", "result_b", id="type_b_processing"),
    ],
)
def test_process_data_by_type(data_type: str, expected: str) -> None:
    data = create_data(data_type)
    result = process(data)
    assert result == expected, f"Processing {data_type} should yield {expected}"
```

### No pytest.raises Without match=

```python
# BAD - no match pattern
def test_invalid_input():
    with pytest.raises(ValueError):
        process(None)

# GOOD - explicit match pattern
def test_invalid_input_raises_with_message() -> None:
    with pytest.raises(ValueError, match="Input cannot be None"):
        process(None)
```

---

## Assertion Requirements

Every assertion MUST include a descriptive message.

### Plain Assertions

```python
# BAD
assert result == expected

# GOOD
assert result == expected, f"Expected {expected} but got {result}"
```

### Comparison Assertions

```python
# BAD
assert len(items) == 3

# GOOD
assert len(items) == 3, f"Expected 3 items, found {len(items)}"
```

### Boolean Assertions

```python
# BAD
assert is_valid

# GOOD
assert is_valid, f"Expected validation to pass for input: {input_data}"
```

### Collection Assertions

```python
# BAD
assert item in collection

# GOOD
assert item in collection, f"Expected {item!r} to be in {collection!r}"
```

---

## Magic Value Prevention

### Use Constants

```python
# BAD - magic numbers
def test_timeout():
    assert response_time < 5000

# GOOD - named constant
RESPONSE_TIMEOUT_MS = 5000

def test_response_within_timeout() -> None:
    assert response_time < RESPONSE_TIMEOUT_MS, (
        f"Response took {response_time}ms, exceeds {RESPONSE_TIMEOUT_MS}ms limit"
    )
```

### Use Fixtures

```python
# BAD - inline magic value
def test_user_creation():
    user = create_user("test@example.com", "sample-test-password")
    assert user.email == "test@example.com"

# GOOD - fixture provides test data
@pytest.fixture
def test_credentials() -> dict[str, str]:
    return {"email": "test@example.com", "password": "sample-test-password"}

def test_user_creation(test_credentials: dict[str, str]) -> None:
    user = create_user(**test_credentials)
    assert user.email == test_credentials["email"], (
        f"User email should be {test_credentials['email']}"
    )
```

### Use Parametrize for Variations

```python
# BAD - multiple magic values
def test_price_calculation():
    assert calculate_price(100) == 110
    assert calculate_price(200) == 220

# GOOD - parametrized with clear meaning
@pytest.mark.parametrize(
    ("base_price", "expected_total"),
    [
        pytest.param(100, 110, id="base_100_with_10pct_tax"),
        pytest.param(200, 220, id="base_200_with_10pct_tax"),
        pytest.param(0, 0, id="zero_price_no_tax"),
    ],
)
def test_price_calculation_with_tax(base_price: int, expected_total: int) -> None:
    result = calculate_price(base_price)
    assert result == expected_total, (
        f"Price {base_price} with tax should be {expected_total}, got {result}"
    )
```

---

## Fixture Guidelines

### Scope Selection

| Scope | Use When |
|-------|----------|
| `function` | Default. State must be fresh per test. |
| `class` | Tests in a class share setup (use sparingly). |
| `module` | Expensive setup shared by all tests in file. |
| `session` | Very expensive, immutable resources (DB connections). |

### Fixture Location

```
tests/
├── conftest.py          # Shared fixtures (root level)
├── unit/
│   ├── conftest.py      # Unit test fixtures
│   └── test_*.py
├── integration/
│   ├── conftest.py      # Integration fixtures (DB, etc.)
│   └── test_*.py
```

### Fixture Dependencies

```python
# Fixtures can depend on other fixtures
@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """Create session from engine fixture."""
    session = Session(db_engine)
    yield session
    session.rollback()
```

### Type Annotations

```python
# Always annotate fixture return types
@pytest.fixture
def sample_meeting() -> Meeting:
    """Provide a sample meeting for tests."""
    return Meeting(id=MeetingId.generate(), title="Test Meeting")
```

---

## Test Naming Convention

### Pattern

```
test_<unit>_<scenario>_<expected_outcome>
```

### Examples

```python
# Function under test + scenario + outcome
def test_parse_date_valid_iso_format_returns_datetime() -> None: ...
def test_parse_date_invalid_string_raises_value_error() -> None: ...
def test_user_login_correct_credentials_returns_token() -> None: ...
def test_user_login_wrong_password_raises_auth_error() -> None: ...
```

### Markers for Slow/Integration Tests

```python
@pytest.mark.slow
def test_full_pipeline_large_dataset_completes_successfully() -> None: ...

@pytest.mark.integration
def test_database_connection_valid_url_connects() -> None: ...
```

---

## Test Classification

Tests must verify one of these qualities:

### 1. Function (Correctness)

Does it produce the right output?

```python
def test_add_two_numbers_returns_sum() -> None:
    result = add(2, 3)
    assert result == 5, "add(2, 3) should return 5"
```

### 2. Behavior (State/Side Effects)

Does it cause the right state changes?

```python
def test_save_meeting_persists_to_database(db_session: Session) -> None:
    meeting = Meeting(title="Test")
    save_meeting(db_session, meeting)
    stored = db_session.query(Meeting).first()
    assert stored is not None, "Meeting should be persisted after save"
    assert stored.title == "Test", "Persisted meeting should retain title"
```

### 3. Robustness (Error Handling)

Does it handle edge cases and errors gracefully?

```python
def test_divide_by_zero_raises_descriptive_error() -> None:
    with pytest.raises(ZeroDivisionError, match="Cannot divide by zero"):
        divide(10, 0)
```

### 4. Rigor (Boundary Conditions)

Does it handle boundaries correctly?

```python
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(0, True, id="minimum_valid"),
        pytest.param(100, True, id="maximum_valid"),
        pytest.param(-1, False, id="below_minimum"),
        pytest.param(101, False, id="above_maximum"),
    ],
)
def test_validate_range_boundary_conditions(value: int, expected: bool) -> None:
    result = validate_range(value, min_val=0, max_val=100)
    assert result == expected, f"validate_range({value}) should be {expected}"
```

### Tests to Avoid

**Structure-only tests** that verify implementation details:

```python
# BAD - tests structure, not behavior
def test_meeting_has_id_attribute():
    meeting = Meeting()
    assert hasattr(meeting, "id")

# GOOD - tests actual functionality
def test_meeting_generates_unique_id_on_creation() -> None:
    meeting1 = Meeting()
    meeting2 = Meeting()
    assert meeting1.id != meeting2.id, "Each meeting should have a unique ID"
```

Absorb structure checks into meaningful tests or remove them.
