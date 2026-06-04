
# Python Error Handling

Enforcer hooks block broad exception handlers (PY-EXC-001), silent broad exceptions (PY-EXC-002), datetime.now() fallbacks (PY-QUALITY-004), default value swallowing (PY-QUALITY-005), and silent None returns (PY-QUALITY-006).

## Do This

- **Domain exceptions**: `raise StorageTimeoutError("msg")` — not generic `Exception`
- **Chain exceptions**: Always `raise ... from err` to preserve stack traces
- **Structured logging**: Use project-standard loggers, not `print()` (PY-LOG-001 blocks stdlib logger creation)
- **Graceful degradation**: Implement fallback logic for non-critical failures in distributed/networked code
- **Retry with backoff**: Exponential backoff for transient network errors
- **User-facing errors**: Helpful messages that don't leak system internals

## Exception Patterns

```python
# Good — specific, chained
try:
    result = await client.fetch(url)
except httpx.TimeoutException as err:
    raise ServiceTimeoutError(f"upstream timeout: {url}") from err

# Good — explicit fallback with logging
try:
    config = load_config(path)
except FileNotFoundError:
    logger.warning("Config not found at %s, using defaults", path)
    config = DEFAULT_CONFIG
```

## Not This

- `except Exception: pass` — swallows everything silently
- `except Exception: return None` — hides failures behind None
- `except Exception: return datetime.now()` — fabricates data on failure
- `except Exception as e: return default_value` — swallows with a default

## Exception Hierarchy

Define a base exception for your package, then derive specific ones:

```python
# my_package/exceptions.py
class MyPackageError(Exception):
    """Base for all package errors."""

class ConfigError(MyPackageError):
    """Invalid or missing configuration."""

class StorageTimeoutError(MyPackageError):
    """Upstream storage did not respond in time."""

class ValidationError(MyPackageError):
    """Input failed validation."""
```

Callers can catch `MyPackageError` for any package failure, or specific subclasses for targeted handling. This replaces broad `except Exception` with meaningful, catchable types.

## Recovery Pattern for Exception Hooks

- Replace broad catches with the specific expected exception type.
- If the failure is recoverable, log structured context and return an explicit domain fallback.
- If the failure indicates corruption/infrastructure trouble, raise a package-specific exception with `raise ... from err`.
- Never satisfy PY-QUALITY-005/006 by adding suppressions or generic defaults; preserve failure semantics.
