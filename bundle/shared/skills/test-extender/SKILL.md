---
name: test-extender
description: Extend Python test suites with parametrization, fixture reuse, and quality enforcement. Use when asked to add tests, extend existing tests, improve test coverage, consolidate duplicate tests, or fix test quality issues. Triggers on requests like "add tests for X", "extend these tests", "parametrize tests", "consolidate tests", "fix test quality", or "improve test coverage".
---

# Test Extender

Extend pytest test suites by finding existing tests, evaluating parametrization opportunities, reusing fixtures, and enforcing quality standards.

## Workflow

### 1. Discover Existing Tests

Run analysis script to find tests and identify issues:

```bash
python scripts/analyze_tests.py tests/ --json
```

Or search with ripgrep for specific patterns:

```bash
# Find tests for a specific function
rg "def test_.*<function_name>" tests/ -l

# Find parametrized tests
rg "@pytest.mark.parametrize" tests/ -A5

# Find tests with loops (anti-pattern)
rg "for .* in .*:" tests/test_*.py -B2 -A2
```

Use semantic search via Serena tools:

```
find_symbol(name_path_pattern="test_*", relative_path="tests/", include_kinds=[12])
```

### 2. Discover Fixtures

Run fixture discovery:

```bash
python scripts/find_fixtures.py tests/ --with-usage --json
```

Check conftest hierarchy:

```bash
rg "@pytest.fixture" tests/**/conftest.py -A3
```

### 3. Evaluate Extension Opportunities

**Parametrization candidates:**
- Multiple similar test functions (test_foo_case1, test_foo_case2)
- Tests with loops or conditionals
- Tests with 3+ assertions on similar values

**Fixture reuse opportunities:**
- Repeated setup code across tests
- Common object construction patterns
- Shared test data

### 4. Implement Extensions

Follow quality rules strictly. See [references/quality_rules.md](references/quality_rules.md).

**Key requirements:**
- No loops or conditionals in test bodies
- All assertions include descriptive messages
- No magic values (use constants, fixtures, parametrize)
- Use `pytest.param()` with `id=` for named cases
- Match naming: `test_<unit>_<scenario>_<expected>`

See [references/parametrization_patterns.md](references/parametrization_patterns.md) for patterns.

### 5. Validate Quality

```bash
make quality
```

**Progress gate:** Acknowledge guidelines compliance before proceeding.

## Quick Reference

### Parametrize Pattern

```python
@pytest.mark.parametrize(
    ("input_val", "expected"),
    [
        pytest.param(1, 2, id="simple_case"),
        pytest.param(0, 0, id="zero_case"),
    ],
)
def test_double_value(input_val: int, expected: int) -> None:
    result = double(input_val)
    assert result == expected, f"double({input_val}) should be {expected}"
```

### Fixture Scopes

| Scope | When |
|-------|------|
| `function` | Fresh state per test (default) |
| `module` | Expensive setup, shared in file |
| `session` | Very expensive, immutable |

### Test Classification

Tests must verify: **function** (correctness), **behavior** (state changes), **robustness** (error handling), or **rigor** (boundaries).

Structure-only tests should be absorbed into meaningful tests or removed.

## Troubleshooting

### Fixture Consolidation with Duplicate-Check Hooks

When hooks block duplicate fixture definitions, follow this order:

**Problem:** Cannot add fixture to conftest.py because hook detects duplicate with test file.

**Solution 1: Use intermediate conftest.py**
```
# If consolidating from tests/grpc/test_foo.py:
# 1. Add fixture to tests/grpc/conftest.py (not tests/conftest.py)
# 2. Remove fixture from tests/grpc/test_foo.py
# 3. Tests inherit from nearest conftest.py in hierarchy
```

**Solution 2: Rename-then-migrate**
```python
# In test file, temporarily rename:
@pytest.fixture
def _local_sample_config() -> Config:  # Renamed to avoid conflict
    ...

# Now add to conftest.py with original name
# Then remove _local_sample_config from test file
```

**Key insight:** The conftest.py hierarchy allows fixtures in `tests/grpc/conftest.py` to serve all tests under `tests/grpc/` without conflicting with `tests/conftest.py`.

### Loop-to-Parametrize Conversion

When converting loops to parametrization, split into separate test functions if the loop body has multiple assertions:

```python
# Before (anti-pattern):
def test_states() -> None:
    for state in (A, B, C):
        assert state in valid_states
        obj = create(state=state)
        assert obj.should_skip

# After (two parametrized tests):
@pytest.mark.parametrize("state", [pytest.param(A, id="a"), ...])
def test_state_is_valid(state: State) -> None:
    assert state in valid_states, f"{state} should be valid"

@pytest.mark.parametrize("state", [pytest.param(A, id="a"), ...])
def test_state_triggers_skip(state: State) -> None:
    obj = create(state=state)
    assert obj.should_skip, f"{state} should trigger skip"
```

## Resources

- `scripts/analyze_tests.py` - Find tests, detect anti-patterns
- `scripts/find_fixtures.py` - Discover fixtures, analyze scope/usage
- `references/quality_rules.md` - Complete quality rules
- `references/parametrization_patterns.md` - Parametrization examples
