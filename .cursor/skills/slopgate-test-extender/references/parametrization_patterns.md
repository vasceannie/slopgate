# Parametrization Patterns Reference

Common patterns for extending tests with `pytest.mark.parametrize`.

## Table of Contents

1. [Basic Parametrization](#basic-parametrization)
2. [Multiple Parameters](#multiple-parameters)
3. [Named Test Cases](#named-test-cases)
4. [Fixture Parametrization](#fixture-parametrization)
5. [Conditional Skipping](#conditional-skipping)
6. [Indirect Parametrization](#indirect-parametrization)
7. [Consolidation Patterns](#consolidation-patterns)

---

## Basic Parametrization

### Simple Value List

```python
@pytest.mark.parametrize("input_val", [1, 2, 3, 5, 8])
def test_fibonacci_values_are_valid(input_val: int) -> None:
    result = is_fibonacci(input_val)
    assert result is True, f"{input_val} should be recognized as Fibonacci number"
```

### Input-Output Pairs

```python
@pytest.mark.parametrize(
    ("input_val", "expected"),
    [
        (0, 0),
        (1, 1),
        (5, 120),
        (10, 3628800),
    ],
)
def test_factorial_returns_expected_value(input_val: int, expected: int) -> None:
    result = factorial(input_val)
    assert result == expected, f"factorial({input_val}) should be {expected}"
```

---

## Multiple Parameters

### Tuple Unpacking

```python
@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (1, 2, 3),
        (0, 0, 0),
        (-1, 1, 0),
        (100, 200, 300),
    ],
)
def test_add_returns_sum(a: int, b: int, expected: int) -> None:
    result = add(a, b)
    assert result == expected, f"add({a}, {b}) should equal {expected}"
```

### Object Construction

```python
@pytest.mark.parametrize(
    ("name", "email", "expected_valid"),
    [
        ("Alice", "alice@example.com", True),
        ("Bob", "invalid-email", False),
        ("", "empty@example.com", False),
    ],
)
def test_user_validation(name: str, email: str, expected_valid: bool) -> None:
    user = User(name=name, email=email)
    result = user.is_valid()
    assert result == expected_valid, (
        f"User({name!r}, {email!r}).is_valid() should be {expected_valid}"
    )
```

---

## Named Test Cases

### pytest.param with IDs

```python
@pytest.mark.parametrize(
    ("status_code", "expected_category"),
    [
        pytest.param(200, "success", id="ok"),
        pytest.param(201, "success", id="created"),
        pytest.param(400, "client_error", id="bad_request"),
        pytest.param(404, "client_error", id="not_found"),
        pytest.param(500, "server_error", id="internal_error"),
    ],
)
def test_categorize_http_status(status_code: int, expected_category: str) -> None:
    result = categorize_status(status_code)
    assert result == expected_category, (
        f"Status {status_code} should be '{expected_category}'"
    )
```

### Descriptive IDs for Complex Cases

```python
@pytest.mark.parametrize(
    ("config", "expected_behavior"),
    [
        pytest.param(
            {"timeout": 30, "retries": 3},
            "standard",
            id="standard_config",
        ),
        pytest.param(
            {"timeout": 0, "retries": 0},
            "fail_fast",
            id="zero_tolerance_config",
        ),
        pytest.param(
            {"timeout": 300, "retries": 10},
            "resilient",
            id="high_availability_config",
        ),
    ],
)
def test_determine_behavior_from_config(
    config: dict[str, int], expected_behavior: str
) -> None:
    result = determine_behavior(config)
    assert result == expected_behavior, (
        f"Config {config} should result in '{expected_behavior}' behavior"
    )
```

---

## Fixture Parametrization

### Parametrized Fixtures

```python
@pytest.fixture(params=["sqlite", "postgresql", "mysql"])
def db_engine(request: pytest.FixtureRequest) -> Engine:
    """Provide database engines for different backends."""
    return create_engine(f"{request.param}://...")

def test_query_executes_on_all_backends(db_engine: Engine) -> None:
    result = db_engine.execute("SELECT 1")
    assert result is not None, f"Query should succeed on {db_engine.name}"
```

### Fixture with IDs

```python
@pytest.fixture(
    params=[
        pytest.param({"debug": True}, id="debug_mode"),
        pytest.param({"debug": False}, id="production_mode"),
    ]
)
def app_config(request: pytest.FixtureRequest) -> dict[str, bool]:
    """Provide application configurations."""
    return request.param
```

---

## Conditional Skipping

### Skip Specific Cases

```python
@pytest.mark.parametrize(
    ("platform", "feature"),
    [
        pytest.param("windows", "registry", id="windows_registry"),
        pytest.param("linux", "systemd", id="linux_systemd"),
        pytest.param(
            "macos",
            "launchd",
            marks=pytest.mark.skip(reason="macOS CI not configured"),
            id="macos_launchd",
        ),
    ],
)
def test_platform_feature(platform: str, feature: str) -> None:
    result = check_feature(platform, feature)
    assert result, f"{feature} should be available on {platform}"
```

### Expected Failures

```python
@pytest.mark.parametrize(
    ("input_val", "expected"),
    [
        pytest.param(1, 1, id="simple"),
        pytest.param(
            -1,
            1,
            marks=pytest.mark.xfail(reason="Negative input handling pending"),
            id="negative_input",
        ),
    ],
)
def test_absolute_value(input_val: int, expected: int) -> None:
    result = absolute(input_val)
    assert result == expected, f"absolute({input_val}) should be {expected}"
```

---

## Indirect Parametrization

### Transform Parameters via Fixture

```python
@pytest.fixture
def user_by_role(request: pytest.FixtureRequest) -> User:
    """Create user based on role parameter."""
    role = request.param
    return User(name=f"{role}_user", role=role)

@pytest.mark.parametrize(
    "user_by_role",
    ["admin", "editor", "viewer"],
    indirect=True,
)
def test_user_permissions(user_by_role: User) -> None:
    permissions = user_by_role.get_permissions()
    assert len(permissions) > 0, (
        f"User with role {user_by_role.role} should have permissions"
    )
```

---

## Consolidation Patterns

### Merging Similar Tests

Before (separate tests):

```python
def test_parse_valid_json_object() -> None:
    result = parse('{"key": "value"}')
    assert result == {"key": "value"}

def test_parse_valid_json_array() -> None:
    result = parse('[1, 2, 3]')
    assert result == [1, 2, 3]

def test_parse_valid_json_string() -> None:
    result = parse('"hello"')
    assert result == "hello"
```

After (consolidated):

```python
@pytest.mark.parametrize(
    ("json_input", "expected"),
    [
        pytest.param('{"key": "value"}', {"key": "value"}, id="object"),
        pytest.param("[1, 2, 3]", [1, 2, 3], id="array"),
        pytest.param('"hello"', "hello", id="string"),
        pytest.param("123", 123, id="number"),
        pytest.param("true", True, id="boolean"),
        pytest.param("null", None, id="null"),
    ],
)
def test_parse_valid_json(json_input: str, expected: object) -> None:
    result = parse(json_input)
    assert result == expected, f"parse({json_input!r}) should return {expected!r}"
```

### Merging Error Cases

Before (separate tests):

```python
def test_parse_invalid_json_unclosed_brace() -> None:
    with pytest.raises(JSONDecodeError):
        parse('{"key": "value"')

def test_parse_invalid_json_trailing_comma() -> None:
    with pytest.raises(JSONDecodeError):
        parse('[1, 2, 3,]')
```

After (consolidated):

```python
@pytest.mark.parametrize(
    "invalid_json",
    [
        pytest.param('{"key": "value"', id="unclosed_brace"),
        pytest.param("[1, 2, 3,]", id="trailing_comma"),
        pytest.param("{'single': 'quotes'}", id="single_quotes"),
        pytest.param("", id="empty_string"),
    ],
)
def test_parse_invalid_json_raises_error(invalid_json: str) -> None:
    with pytest.raises(JSONDecodeError, match=""):
        parse(invalid_json)
```

### Extracting Common Setup

Before (duplicated setup):

```python
def test_meeting_start_recording() -> None:
    meeting = Meeting(id=MeetingId.generate(), title="Test")
    meeting.start_recording()
    assert meeting.is_recording

def test_meeting_stop_recording() -> None:
    meeting = Meeting(id=MeetingId.generate(), title="Test")
    meeting.start_recording()
    meeting.stop_recording()
    assert not meeting.is_recording
```

After (with fixture):

```python
@pytest.fixture
def active_meeting() -> Meeting:
    """Provide a meeting ready for operations."""
    return Meeting(id=MeetingId.generate(), title="Test")

def test_meeting_start_recording(active_meeting: Meeting) -> None:
    active_meeting.start_recording()
    assert active_meeting.is_recording, "Meeting should be recording after start"

def test_meeting_stop_recording(active_meeting: Meeting) -> None:
    active_meeting.start_recording()
    active_meeting.stop_recording()
    assert not active_meeting.is_recording, "Meeting should stop recording after stop"
```

---

## Decision Guide

| Situation | Approach |
|-----------|----------|
| Same test logic, different inputs | `@pytest.mark.parametrize` |
| Same setup, different tests | Fixture |
| Loop over test cases | Convert to parametrize |
| Conditional assertions | Split or parametrize |
| 3+ similar tests | Consolidate with parametrize |
| Complex object construction | Fixture with params |
| Platform-specific tests | Parametrize with skip marks |
