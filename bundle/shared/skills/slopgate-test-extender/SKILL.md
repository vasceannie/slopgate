---
name: slopgate-test-extender
description: |
  Extend Python test suites with parametrization, fixture reuse, and quality enforcement. Use when asked to add tests, extend existing tests, improve test coverage, consolidate duplicate tests, fix test quality issues, or when Slopgate reports untested-production-code, missing test references, or coverage gaps. Triggers on requests like "add tests for X", "extend these tests", "parametrize tests", "consolidate tests", "fix test quality", "improve test coverage", "write tests for this function", "test this module", "behavior tests", "integration tests", "missing tests", "coverage holes", "untested code", or when a hook denies with test-related findings.
version: 1.0.0
author: Slopgate
license: MIT
compatibility: claude-code, opencode, codex, hermes, slopgate
metadata:
  hermes:
    tags: [slopgate,testing,pytest,hypothesis,coverage]
    related_skills: [slopgate-code-hygiene-refactor,slopgate-hygiene-orchestrator]
  slopgate:
    rule_ids: [untested-production-code,hypothesis-candidate,test-integrity,weak-assertion,loop-to-parametrize]
    activation:
      primary: [missing tests,coverage gaps,parametrization,property testing,weak assertions]
      avoid: [production-only refactor,broad lint cleanup,helper ownership discovery]
---

# Test Extender

Extend pytest test suites by finding existing tests, evaluating parametrization opportunities, reusing fixtures, and enforcing quality standards.

## When to Use

Use when the primary work is test coverage, test quality, parametrization, fixtures, or property-based testing.

- Slopgate reports `untested-production-code`, `hypothesis-candidate`, `test-integrity`, weak assertions, loop-to-parametrize findings, or missing test references.
- User asks to add tests, extend tests, improve coverage, parametrize examples, or decide between finite examples and Hypothesis.
- Use alongside production refactor skills only after the production seam is clear.

## When Not to Use

Do not use as the primary skill for production-only structure failures. Use `slopgate-code-hygiene-refactor` first, then return here for coverage.

Do not add Hypothesis just because it sounds stronger: use parametrization for finite named examples and Hypothesis for broad domains/invariants.

Do not use for repo-wide lint orchestration; use `slopgate-hygiene-orchestrator`.

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
- Finite, explicit edge-case sets (empty, single, max, boundary)

**Property-based / Hypothesis candidates:**
- Functions with wide input domains (strings, numbers, collections)
- Invariants that should hold for ALL inputs (round-trip, idempotency, monotonicity)
- Complex state machines or parsers where enumerating cases is infeasible
- Code that processes untrusted/external data
- When the test would need 10+ parametrized cases to feel confident

**Decision rule:**
- Start with parametrization for known edge cases and behavioral examples.
- Add Hypothesis when the input space is large, the invariant is strong, or the function processes arbitrary data.
- Both can coexist: parametrize the known-critical cases, use Hypothesis for the general invariant.
- Do not add Hypothesis as a new project dependency without checking project policy; if it is unavailable and dependency changes are out of scope, write named parametrized examples and leave the property-test recommendation explicit.

**Fixture reuse opportunities:**
- Repeated setup code across tests
- Common object construction patterns
- Shared test data

**Coverage gap candidates (from Slopgate `untested-production-code`):**
- Public symbols with `static_test_reference_coverage=0%`
- Functions/classes with no test references
- New code written without accompanying tests

### 4. Implement Extensions

Follow quality rules strictly. See [references/quality_rules.md](references/quality_rules.md).

**Key requirements:**
- No loops or conditionals in test bodies
- All assertions include descriptive messages
- No magic values (use constants, fixtures, parametrize)
- Use `pytest.param()` with `id=` for named cases
- Match naming: `test_<unit>_<scenario>_<expected>`

**Parametrize vs Hypothesis — implementation guidance:**

| Aspect | Parametrize | Hypothesis |
|--------|-------------|------------|
| **When** | Known edge cases, explicit examples | Large input space, universal invariants |
| **Import** | `import pytest` | `from hypothesis import given, strategies as st` |
| **Decorator** | `@pytest.mark.parametrize("x,y", [...])` | `@given(st.integers())` |
| **Cases** | Explicit: `[(1, 2), (0, 0)]` | Generated: `st.text(), st.lists(st.integers())` |
| **Best for** | Behavior examples, regression cases, boundary values | Round-trips, parsers, validators, idempotency |
| **Avoid** | 10+ hand-written cases for simple invariants | When the "property" is just reimplementing the function |

**Parametrize example:**
```python
@pytest.mark.parametrize(
    ("input_val", "expected"),
    [
        pytest.param(1, 2, id="simple_case"),
        pytest.param(0, 0, id="zero_case"),
        pytest.param(-1, -2, id="negative_case"),
    ],
)
def test_double_value(input_val: int, expected: int) -> None:
    result = double(input_val)
    assert result == expected, f"double({input_val}) should be {expected}"
```

**Hypothesis example:**
```python
from hypothesis import given, strategies as st

@given(st.lists(st.integers()))
def test_reverse_twice_returns_original(values: list[int]) -> None:
    result = reverse(reverse(values))
    assert result == values, "reversing twice should preserve the original list"

@given(st.text())
def test_serialize_roundtrip(raw: str) -> None:
    """parse(serialize(x)) == x"""
    assert parse(serialize(raw)) == raw, "round-trip should preserve data"
```

**Coexistence pattern:**
```python
# Known-critical cases as parametrize
@pytest.mark.parametrize("raw", [
    pytest.param("", id="empty"),
    pytest.param("\x00", id="null_byte"),
    pytest.param("a" * 10000, id="huge_string"),
])
def test_parse_known_cases(raw: str) -> None:
    assert parse(raw) is not None

# General invariant as hypothesis
@given(st.text())
def test_parse_never_crashes(raw: str) -> None:
    result = parse(raw)  # should not raise
    assert isinstance(result, (ParseResult, type(None)))
```

**Responding to `untested-production-code` findings:**

1. Read the Slopgate output for the unreferenced symbol(s) and the suggested scaffold.
2. Identify the public behavior users depend on — not just the function signature.
3. Add behavior/integration tests around the public entrypoint.
4. Avoid testing every helper directly; prefer observable behavior through the public API.
5. If the symbol is dead API, consider deleting or private-scoping instead of adding tests.
6. Verify with `pytest <affected_tests>` and re-run `slopgate lint check`.

See [references/parametrization_patterns.md](references/parametrization_patterns.md) for patterns.
See [references/hypothesis_patterns.md](references/hypothesis_patterns.md) for property-based testing patterns.

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

### Hypothesis Pattern

```python
from hypothesis import given, strategies as st

@given(st.lists(st.integers()))
def test_reverse_twice_returns_original(values: list[int]) -> None:
    result = reverse(reverse(values))
    assert result == values, "reversing twice should preserve the original list"
```

### Coexistence Pattern

```python
# Explicit edge cases via parametrize
@pytest.mark.parametrize("raw", [
    pytest.param("", id="empty"),
    pytest.param("\x00", id="null_byte"),
])
def test_parse_edge_cases(raw: str) -> None:
    assert parse(raw) is not None

# General invariant via hypothesis
@given(st.text())
def test_parse_never_crashes(raw: str) -> None:
    result = parse(raw)  # should not raise
    assert isinstance(result, (ParseResult, type(None)))
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
- `references/hypothesis_patterns.md` - Property-based testing examples
