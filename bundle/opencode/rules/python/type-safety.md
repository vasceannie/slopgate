
# Python Type Safety

Enforcer hooks block `Any` (PY-TYPE-001) and type suppressions (PY-TYPE-002). Write typed code from the start.

## Reach for Specifics First

- **`Protocol`** for structural typing — define the interface you need, not a base class
- **`TypeVar`** for generic functions — `T = TypeVar("T", bound=SomeBase)`
- **`TypedDict`** for dict shapes — especially JSON/API payloads
- **Narrow unions** (`str | int | None`) instead of `Any`
- **`Final`** for constants — immutable by default unless mutation is required

## Type Narrowing — Do It Inline

Narrow at point of use with guard clauses:
```python
# Good — narrow inline
if x is None:
    return default
# x is narrowed to non-None here

# Good — isinstance guard
if isinstance(value, str):
    return value.upper()
```

Avoid `is_valid_foo()` predicates unless the check is reused 3+ times. When justified, use `TypeGuard[T]` or `TypeIs[T]` return annotations.

## Discriminated Unions

Use `type` or `kind` literal fields for complex polymorphic data:
```python
class FileEvent(TypedDict):
    kind: Literal["created", "deleted"]
    path: str
```

## Not This

- `Any` — use `object` or a Protocol instead
- `# type: ignore`, `# noqa`, `# pyright: ignore`, `# pylint: disable` — fix the root cause with Protocols, TypedDicts, overloads, or local stubs
- `cast()` without justification — narrow with isinstance or TypeGuard instead

## Concrete Examples

### Protocol — define the interface you need

```python
from typing import Protocol

class Serializable(Protocol):
    def to_dict(self) -> dict[str, object]: ...

def save(obj: Serializable) -> None:
    data = obj.to_dict()  # works with any class that has to_dict()
```

### TypeVar — generic without losing type info

```python
from typing import TypeVar

T = TypeVar("T")

def first(items: list[T]) -> T | None:
    return items[0] if items else None

# Caller gets the right type back:
name: str | None = first(["alice", "bob"])  # T = str
```

### TypedDict — structured dicts for JSON/API

```python
from typing import TypedDict

class UserPayload(TypedDict):
    id: int
    email: str
    active: bool

def process_user(data: UserPayload) -> str:
    return data["email"]  # type-safe key access
```

## Third-Party or Incomplete Types

- `PY-TYPE-002` blocks suppressions; do not trade type safety for silence.
- Prefer a local `Protocol`, `TypedDict`, overload, or `.pyi` stub for untyped library seams.
- Use `TypeGuard`/`TypeIs` only when the predicate actually narrows the value at call sites.
