---
globs: **/test_*.py, **/*_test.py, **/tests/**/*.py, **/conftest.py
---

# Pytest Patterns

## conftest.py

- **Scope hierarchy:** fixtures live in the narrowest conftest that needs them (root → unit/ → integration/).
- **Never `from conftest import ...`** — pytest injects automatically. If you're importing, it's not a fixture; move to a helper module.
- Noun fixture names (`db_session`, not `make_session`).
- `yield` fixtures for setup/teardown — cleanup runs regardless of pass/fail:
  ```python
  @pytest.fixture
  def db_session(engine):
      session = Session(engine)
      yield session
      session.rollback(); session.close()
  ```

## Scopes

| Scope | Lifetime | Use |
|---|---|---|
| `function` (default) | each test | most fixtures |
| `class` | per class | shared setup (rare) |
| `module` | per file | expensive setup shared in a file |
| `session` | full run | DB engine, Docker, app startup |

- Session/module-scoped fixtures must be stateless or read-only. Mutable session fixtures contaminate.
- Higher scopes can't depend on lower scopes.

## Marks

```python
@pytest.mark.slow            # pytest -m "not slow"
@pytest.mark.integration
@pytest.mark.smoke
@pytest.mark.skipif(sys.platform == "win32", reason="Unix-only")
@pytest.mark.xfail(reason="bug #456", strict=True)

@pytest.mark.parametrize("input,expected", [
    ("valid@email.com", True),
    ("no-at-sign", False),
], ids=["valid", "missing-at"])
def test_validate_email(input, expected): ...
```

Register custom marks in `pyproject.toml` to silence `PytestUnknownMarkWarning`.

## Organization

- Test files mirror source: `src/auth/service.py` → `tests/unit/test_auth_service.py`.
- Static fixtures in `tests/fixtures/`, loaded via `pathlib.Path(__file__).parent / "fixtures"`.
- No test logic in `__init__.py`.

## Config

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q --strict-markers"
filterwarnings = ["error"]
```

## Hook repairs

- `PY-TEST-003`: replace loops-with-asserts with `@pytest.mark.parametrize` + `ids=[...]`.
- `PY-TEST-004`: shared fixtures → narrowest `conftest.py`.
- 3+ adjacent bare asserts → add messages or split by behavior.
