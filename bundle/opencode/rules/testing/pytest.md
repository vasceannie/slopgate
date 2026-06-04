
# Pytest Patterns

## conftest.py

conftest.py is pytest's dependency injection system. Use it deliberately.

- **Scope hierarchy**: Place fixtures at the narrowest conftest that needs them
  ```
  tests/
  ├── conftest.py              # shared: db session, test client, auth helpers
  ├── unit/
  │   ├── conftest.py          # unit-only: mock factories, isolated fixtures
  │   └── test_models.py
  └── integration/
      ├── conftest.py          # integration-only: real DB, seeded data
      └── test_api.py
  ```
- **Never import from conftest** — pytest injects fixtures automatically. If you're writing `from conftest import ...`, it's not a fixture — move it to a helper module
- **Fixture naming**: noun for what it provides (`db_session`, `auth_client`, `sample_user`), not verb
- **`yield` fixtures** for setup/teardown — cleanup runs after the test regardless of pass/fail:
  ```python
  @pytest.fixture
  def db_session(engine):
      session = Session(engine)
      yield session
      session.rollback()
      session.close()
  ```

## Fixture Scopes

| Scope | Lifetime | Use For |
|---|---|---|
| `function` (default) | Each test | Most fixtures — isolated, no bleed |
| `class` | Per test class | Shared setup for related tests (rare) |
| `module` | Per test file | Expensive setup shared across a file |
| `session` | Entire test run | DB engine, Docker containers, app startup |

- **IMPORTANT**: Session/module-scoped fixtures must be stateless or read-only. Mutable session fixtures cause cross-test contamination
- Higher-scoped fixtures cannot depend on lower-scoped ones

## Marks

```python
# Categorize tests
@pytest.mark.slow           # skip with: pytest -m "not slow"
@pytest.mark.integration    # run with: pytest -m integration
@pytest.mark.smoke          # quick sanity: pytest -m smoke

# Parametrize instead of copy-paste or loops-with-asserts (PY-TEST-003)
@pytest.mark.parametrize("input,expected", [
    ("valid@email.com", True),
    ("no-at-sign", False),
    ("", False),
], ids=["valid", "missing-at", "empty"])
def test_validate_email(input, expected):
    assert validate_email(input) == expected

# Skip with reason
@pytest.mark.skip(reason="Waiting on upstream fix #123")
@pytest.mark.skipif(sys.platform == "win32", reason="Unix-only")

# Expected failures
@pytest.mark.xfail(reason="Known bug #456", strict=True)
```

- **Register custom marks** in `pyproject.toml` to avoid `PytestUnknownMarkWarning`:
  ```toml
  [tool.pytest.ini_options]
  markers = [
      "slow: marks tests as slow",
      "integration: marks integration tests",
  ]
  ```

## Test Organization

```
tests/
├── conftest.py              # root: shared fixtures, plugins
├── unit/                    # fast, isolated, no I/O
│   ├── test_models.py       # test file mirrors src layout
│   └── test_services.py
├── integration/             # real DB, real HTTP, slower
│   └── test_api.py
└── fixtures/                # static test data (JSON, CSV)
    └── sample_response.json
```

- Test files **mirror source layout**: `src/auth/service.py` → `tests/unit/test_auth_service.py`
- Static test data goes in `tests/fixtures/`, loaded via `pathlib.Path(__file__).parent / "fixtures"`
- **No test logic in `__init__.py`** — keep test packages as plain directories

## Common Pytest Config

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q --strict-markers"
filterwarnings = ["error"]    # treat warnings as errors
```

## Hook-Anchored Pytest Repairs

- `PY-TEST-003`: replace loops containing asserts with `@pytest.mark.parametrize`; include `ids=[...]` for readable failures.
- `PY-TEST-004`: shared fixtures belong in the narrowest useful `conftest.py`, not individual test modules.
- If 3+ bare asserts are adjacent, add descriptive messages or split the test by behavior.
