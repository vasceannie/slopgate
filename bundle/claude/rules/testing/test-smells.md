---
globs: **/test_*.py, **/*_test.py, **/tests/**/*.py, **/*.test.ts, **/*.test.tsx, **/*.spec.ts, **/*.spec.tsx
---

# Test Smells

Hooks block these at edit time.

## Assertion roulette (PY-TEST-001)

Multiple assertions, no messages → which broke? One concept per test, or add messages.

## Conditional assertions (PY-TEST-002/003)

Logic in tests hides which path ran. Split into separate tests, one per case.

## Loops with assertions

```python
# Bad
for item in items:
    assert item.valid

# Good
@pytest.mark.parametrize("item", items, ids=lambda i: i.name)
def test_item_valid(item):
    assert item.valid
```

## `time.sleep()` (PY-TEST-002)

Slow + flaky. Mock time with `unittest.mock.patch` or async test utilities.

## Assertion-free tests

Every test asserts something. Calling code without verifying is a smoke check at best.

## Mock theater

Mocks that replace the behavior under test make fragile code look correct.

```python
# Bad — verifies the mock
handler = MagicMock(return_value={"company": "Acme"})
run_screen.apply_projection(handler())
handler.assert_called()

# Good — real pipeline, real assertion
projection = projection_store.apply(real_field_focused_event(company="Acme"))
run_screen.apply_projection(projection)
assert run_screen.current_company == "Acme"
```

- Don't mock parsers, serializers, event handlers, state stores, projections, renderers, or in-process collaborators when their interaction is the risk.
- If a mock IS needed for a true boundary, assert semantic payload — `assert_called()`/call counts alone are too weak.

## Presence-only assertions

```python
# Bad
assert summary.company is not None
assert result.success is True

# Good
assert summary.company == "Acme"
assert preview.stats.company_text == "Acme"
```

Avoid `is not None`, mounted/rendered-only checks, bare truthiness, `success is True` unless that exact presence is the contract. Avoid raw dicts, `cast()` bypasses, partial fakes when real models/factories/sample payloads exist.

## Leaf-only coverage for pipeline bugs

When the bug lives between layers, widget/unit tests alone are insufficient. Add a thin integration/contract test through parser → enrichment → projection/store → handler that checks the screen-facing state.

## Eager tests (8+ assertions) / long tests (>50 lines)

Testing too many behaviors at once. Split by AAA boundary — one Act per test.
