---
globs: **/*.py
---

# Python Error Handling

Hooks block: broad excepts (PY-EXC-001/002), `datetime.now()` fallbacks (PY-QUALITY-004), default-value swallowing (PY-QUALITY-005), silent None returns (PY-QUALITY-006), `print()` loggers (PY-LOG-001).

## Do

- Raise **domain exceptions** (`StorageTimeoutError`), not generic `Exception`.
- Chain: `raise NewError(...) from err` — preserves stack.
- Structured loggers, not `print()`.
- Explicit fallback only when recoverable, with a log line.
- Exponential backoff for transient network errors.
- User-facing messages don't leak internals.

```python
try:
    result = await client.fetch(url)
except httpx.TimeoutException as err:
    raise ServiceTimeoutError(f"upstream timeout: {url}") from err
```

## Don't

- `except Exception: pass` / `return None` / `return default` / `return datetime.now()` — all swallow failures.

## Exception hierarchy

Define a package base, derive specifics. Callers catch the base for any package failure, subclasses for targeted handling.

```python
class MyPackageError(Exception): ...
class ConfigError(MyPackageError): ...
class StorageTimeoutError(MyPackageError): ...
```

## Hook recovery

- Narrow the catch to the specific expected type.
- Recoverable → log structured context + return explicit domain fallback.
- Infrastructure failure → raise package exception `from err`.
- Never silence PY-QUALITY-005/006 with a suppression or generic default.
