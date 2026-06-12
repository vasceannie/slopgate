# Hypothesis vs pytest parametrization

Use this reference when adding tests for Slopgate test-integrity findings, coverage gaps, parsers, serializers, validators, state transitions, normalization, or broad input domains.

## Decision table

| Situation | Prefer |
|-----------|--------|
| A small finite list of named examples | `pytest.mark.parametrize` |
| Regression cases from bugs or support tickets | `pytest.mark.parametrize` |
| Boundary examples like empty/single/max/invalid | `pytest.mark.parametrize` first |
| The behavior is an invariant over many inputs | Hypothesis |
| The function accepts arbitrary strings, bytes, numbers, lists, dicts, or nested data | Hypothesis |
| The code parses, serializes, normalizes, sorts, filters, validates, or transforms | Hypothesis, plus a few named examples |
| You are about to hand-write 10+ cases for the same rule | Hypothesis |
| The expected output is a fixed exact value for each named input | Parametrize |
| The expected output is a property (round-trip, deterministic, monotonic, bounded, stable ordering) | Hypothesis |

## Use both when appropriate

Property tests should not erase human-readable examples. A good pattern is:

1. Parametrize named edge/regression cases.
2. Add one Hypothesis test for the general invariant.
3. Keep the property simple enough that it does not reimplement production code.

```python
import pytest
from hypothesis import given, strategies as st


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("", id="empty"),
        pytest.param("\x00", id="null_byte"),
        pytest.param("a" * 10_000, id="large_input"),
    ],
)
def test_normalize_named_edge_cases(raw: str) -> None:
    result = normalize(raw)
    assert isinstance(result, str), "normalize should return a string for named edges"


@given(st.text())
def test_normalize_is_idempotent(raw: str) -> None:
    normalized = normalize(raw)
    assert normalize(normalized) == normalized, "normalize should be idempotent"
```

## Good Hypothesis properties

- **Round-trip:** `parse(render(x)) == x`
- **Idempotence:** `normalize(normalize(x)) == normalize(x)`
- **Determinism:** repeated calls with the same input produce the same result
- **Bounds:** output size/value stays within documented limits
- **Monotonicity:** increasing input does not decrease output when the domain promises that
- **Stability:** sorting/ordering is stable for equal keys
- **No-crash:** parser/validator handles arbitrary malformed input without unexpected exceptions
- **Subset/filter:** all output items came from input and satisfy the predicate

## Bad Hypothesis properties

Avoid properties that simply duplicate the implementation:

```python
# Bad: this reproduces the same logic as production.
@given(st.lists(st.integers()))
def test_sum(xs: list[int]) -> None:
    expected = 0
    for x in xs:
        expected += x
    assert custom_sum(xs) == expected
```

Prefer an independent invariant:

```python
@given(st.lists(st.integers()))
def test_sum_is_order_insensitive(xs: list[int]) -> None:
    assert custom_sum(xs) == custom_sum(list(reversed(xs)))
```

## Guardrails for agents

- Do not introduce Hypothesis if the project does not already depend on it without checking project policy first.
- If Hypothesis is unavailable and adding dependencies is out of scope, write parametrized named examples and leave a TODO/note for a property test.
- Keep generated domains bounded when the function is expensive: use `max_size`, `min_value`, `max_value`, or focused strategies.
- Add `@settings(deadline=None)` only when there is a documented reason; do not use it to hide slow tests.
- Use `@example(...)` for known regressions that should always run, or keep those as explicit parametrized cases.
- Prefer public behavior tests over testing private helper internals directly.
