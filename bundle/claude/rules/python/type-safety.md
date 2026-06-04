---
globs: **/*.py
---

# Python Type Safety

Hooks block `Any` (PY-TYPE-001) and suppressions (PY-TYPE-002).

## Reach for specifics

- `Protocol` for structural typing — define what you need, not a base class.
- `TypeVar` for generics (`T = TypeVar("T", bound=Base)`).
- `TypedDict` for JSON/API payload shapes.
- Narrow unions (`str | int | None`) over `Any`.
- `Final` for constants.

## Narrow inline

```python
if x is None:
    return default
# x is non-None below
```

`is_valid_foo()` predicates only if reused 3+ times — use `TypeGuard[T]` / `TypeIs[T]`.

## Discriminated unions

```python
class FileEvent(TypedDict):
    kind: Literal["created", "deleted"]
    path: str
```

## Examples

```python
# Protocol
class Serializable(Protocol):
    def to_dict(self) -> dict[str, object]: ...

# TypedDict
class UserPayload(TypedDict):
    id: int
    email: str
```

## Don't

- `Any` → `object` or `Protocol`.
- `# type: ignore` / `# pyright: ignore` / `# noqa` — fix root cause (Protocol, TypedDict, overload, `.pyi` stub).
- `cast()` without justification — narrow with `isinstance` or `TypeGuard`.

## Untyped third-party

Local `Protocol` / `TypedDict` / overload / `.pyi` stub beats a suppression. Never trade safety for silence.
