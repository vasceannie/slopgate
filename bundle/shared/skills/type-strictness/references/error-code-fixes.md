# Type Error Code Fixes

Mapping of common Pyright and Mypy error codes to specific resolution strategies.

---

## Pyright Error Codes

### reportUnknownMemberType / reportUnknownArgumentType

**Cause**: Expression resolves to `Unknown` (equivalent to implicit `Any`).

**Fix Strategies**:

1. **Add explicit annotation** at source:
```python
# Before
data = json.loads(text)  # Unknown

# After
data: dict[str, str] = json.loads(text)

# Or with TypedDict for structure
class Config(TypedDict):
    host: str
    port: int
config: Config = json.loads(text)
```

2. **Type narrow after retrieval**:
```python
raw = some_untyped_call()
if isinstance(raw, dict):
    # raw is now dict[Unknown, Unknown], narrow further
    assert all(isinstance(k, str) for k in raw.keys())
    typed: dict[str, object] = raw
```

3. **Install type stubs** for the library (see common-stubs.md)

---

### reportUnknownVariableType

**Cause**: Variable type cannot be inferred.

**Fix**:
```python
# Before
items = []  # list[Unknown]

# After
items: list[str] = []

# Or use explicit generic
from collections.abc import MutableSequence
items: MutableSequence[int] = []
```

---

### reportMissingTypeStubs

**Cause**: Import from untyped library.

**Fix Strategies**:

1. **Install stubs**: `pip install types-{package}`

2. **Create local stub** (`.pyi` file):
```python
# _stubs/untyped_module.pyi
def function(arg: str) -> int: ...
class Client:
    def __init__(self, url: str) -> None: ...
    def get(self, path: str) -> bytes: ...
```

3. **Configure stubPath** in pyproject.toml:
```toml
[tool.pyright]
stubPath = "_stubs"
```

---

### reportGeneralTypeIssues

**Cause**: General type mismatch.

**Common Subcases**:

**Incompatible return type**:
```python
# Before - returns str | None but typed as str
def get_name() -> str:
    return cache.get("name")  # Error

# After - fix return type
def get_name() -> str | None:
    return cache.get("name")

# Or - ensure non-None return
def get_name() -> str:
    name = cache.get("name")
    if name is None:
        raise ValueError("Name not in cache")
    return name
```

**Argument type mismatch**:
```python
# Before
def process(value: str) -> None: ...
process(123)  # Error

# After - widen parameter or fix call site
def process(value: str | int) -> None: ...
# OR
process(str(123))
```

---

### reportIncompatibleMethodOverride

**Cause**: Subclass method signature differs from base.

**Fix**:
```python
from typing import override

class Base:
    def process(self, data: bytes) -> str: ...

# Before - incompatible
class Child(Base):
    def process(self, data: str) -> str: ...  # Error

# After - match signature
class Child(Base):
    @override
    def process(self, data: bytes) -> str: ...
```

---

### reportIncompatibleVariableOverride

**Cause**: Class variable type differs from base.

**Fix**:
```python
class Base:
    value: int

# Before
class Child(Base):
    value: str  # Error - incompatible

# After - use compatible type
class Child(Base):
    value: int  # Same type
```

---

### reportPrivateUsage

**Cause**: Accessing private (`_name`) or very private (`__name`) members.

**Fix**: Use public interface or Protocol:
```python
from typing import Protocol

class HasValue(Protocol):
    @property
    def value(self) -> int: ...

def get_value(obj: HasValue) -> int:
    return obj.value  # Use public API
```

---

### reportUnnecessaryCast

**Cause**: Cast to a type that's already known.

**Fix**: Remove the cast:
```python
# Before
x: str = "hello"
y = cast(str, x)  # Unnecessary

# After
x: str = "hello"
y = x
```

---

### reportOptionalMemberAccess

**Cause**: Accessing attribute on potentially `None` value.

**Fix Strategies**:

1. **Guard with None check**:
```python
if obj is not None:
    obj.method()
```

2. **Use walrus operator**:
```python
if (result := get_optional()) is not None:
    use(result)
```

3. **Early return**:
```python
def process(obj: Thing | None) -> str:
    if obj is None:
        return ""
    return obj.name  # obj is Thing here
```

---

### reportUnusedImport / reportUnusedVariable

**Cause**: Import or variable not used.

**Fix**:

For re-exports, use explicit `__all__`:
```python
from module import Thing

__all__ = ["Thing"]  # Marks as intentional re-export
```

For TYPE_CHECKING imports:
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from module import TypeOnlyUsedInAnnotations
```

---

## Mypy Error Codes

### [arg-type]

**Cause**: Argument has incompatible type.

**Fix**: Match expected type or widen function signature:
```python
# Fix at call site
func(int(string_value))

# Or fix function to accept both
def func(value: str | int) -> None: ...
```

---

### [return-value]

**Cause**: Return type incompatible with annotation.

**Fix**: Adjust return type or ensure all paths return correct type:
```python
def get_items() -> list[str]:
    if condition:
        return ["a", "b"]
    return []  # Must return list[str], not None
```

---

### [assignment]

**Cause**: Assigning incompatible type to variable.

**Fix**:
```python
# Before
x: int = "not an int"  # Error

# After - fix value
x: int = 42

# Or - fix annotation
x: str = "not an int"

# Or - narrow with assertion
x: int
raw = get_value()
assert isinstance(raw, int)
x = raw
```

---

### [override]

**Cause**: Method override violates Liskov substitution.

**Fix**: Match base class signature exactly:
```python
class Base:
    def method(self, x: int, y: str = "") -> bool: ...

class Child(Base):
    # Must accept at least same parameters
    def method(self, x: int, y: str = "") -> bool: ...
```

---

### [union-attr]

**Cause**: Attribute access on union where not all types have it.

**Fix**: Narrow the type first:
```python
def process(item: str | bytes | None) -> int:
    if item is None:
        return 0
    # Now item is str | bytes, both have __len__
    return len(item)
```

---

### [index]

**Cause**: Invalid index type or indexing non-indexable.

**Fix**:
```python
# Before
d: dict[str, int] = {}
d[123]  # Error - key must be str

# After
d[str(123)]  # or
d["123"]
```

---

### [misc]

**Cause**: Catch-all for various issues.

**Common fixes**:

**TypedDict key access**:
```python
class Data(TypedDict):
    name: str

def get_field(d: Data, key: str) -> object:
    # Use Mapping for dynamic access
    return dict(d).get(key)
```

---

### [no-untyped-def]

**Cause**: Function missing type annotations.

**Fix**: Add complete annotations:
```python
# Before
def process(data, callback):
    return callback(data)

# After
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")

def process(data: T, callback: Callable[[T], R]) -> R:
    return callback(data)
```

---

### [import-untyped]

**Cause**: Importing from untyped package.

**Fix**: Same as Pyright's reportMissingTypeStubs - install stubs or create local `.pyi` files.

---

## Resolution Decision Tree

```
Error involves Unknown/Any type?
├─ Yes → Is it from third-party library?
│  ├─ Yes → Check for type stubs → Install or create .pyi
│  └─ No → Add explicit annotation at source
├─ No → Is it a return type issue?
│  ├─ Yes → Fix return annotation or ensure all paths return correctly
│  └─ No → Is it argument mismatch?
│     ├─ Yes → Fix call site OR widen parameter type
│     └─ No → Is it attribute access on Optional?
│        ├─ Yes → Add None guard / type narrowing
│        └─ No → Consult specific error code above
```

---

## Forbidden Fixes (Never Do These)

| Temptation | Why Bad | Proper Fix |
|------------|---------|------------|
| `# type: ignore` | Hides real bug | Fix the actual issue |
| `cast(Any, x)` | Defeats type system | Use proper type |
| `from typing import Any` | Type escape hatch | Use specific type |
| Modify pyproject strictness | Hides issues globally | Fix each issue |
| `-> None # type: ignore` | Lying about return | Fix return type |
