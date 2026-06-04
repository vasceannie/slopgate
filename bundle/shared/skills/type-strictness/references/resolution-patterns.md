# Type Resolution Patterns

Patterns for eliminating `Any` through type guards, narrowing, and protocols.

---

## TypeGuard Functions

Create reusable type guards for complex checks:

```python
from typing import TypeGuard

def is_string_list(value: object) -> TypeGuard[list[str]]:
    """Narrow object to list[str]."""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)

def is_valid_config(data: object) -> TypeGuard[dict[str, int]]:
    """Narrow object to config dict."""
    return (
        isinstance(data, dict)
        and all(isinstance(k, str) for k in data.keys())
        and all(isinstance(v, int) for v in data.values())
    )

# Usage
def process(data: object) -> None:
    if is_string_list(data):
        # data is now list[str]
        for item in data:
            print(item.upper())
```

---

## isinstance Narrowing

Narrow union types or objects:

```python
def handle(value: str | int | None) -> str:
    if value is None:
        return "none"
    if isinstance(value, str):
        return value.upper()
    # value is now int
    return str(value)

# Multiple types
def process(data: dict | list | str) -> int:
    if isinstance(data, dict):
        return len(data.keys())
    if isinstance(data, list):
        return len(data)
    return len(data)  # str
```

---

## hasattr Narrowing

For duck typing when Protocol isn't available:

```python
from typing import TYPE_CHECKING

def get_name(obj: object) -> str:
    if hasattr(obj, "name") and isinstance(obj.name, str):
        return obj.name
    if hasattr(obj, "__name__") and isinstance(obj.__name__, str):
        return obj.__name__
    return str(obj)
```

---

## Protocol Definitions

Replace `Any` with structural typing:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Readable(Protocol):
    def read(self, size: int = -1) -> bytes: ...

@runtime_checkable
class HasId(Protocol):
    @property
    def id(self) -> str: ...

# Use instead of Any
def process_file(source: Readable) -> bytes:
    return source.read()

def get_identifier(obj: HasId) -> str:
    return obj.id
```

---

## Callable Typing

Replace `Callable[..., Any]`:

```python
from collections.abc import Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

# Preserve signature
def decorator(func: Callable[P, R]) -> Callable[P, R]:
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return func(*args, **kwargs)
    return wrapper

# Specific signatures
Handler = Callable[[str, int], bool]
Callback = Callable[[], None]
Processor = Callable[[bytes], bytes]
```

---

## Generic Containers

Type container contents:

```python
from typing import TypeVar
from collections.abc import Mapping, Sequence, Iterable

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")

# Instead of list[Any]
def first(items: Sequence[T]) -> T | None:
    return items[0] if items else None

# Instead of dict[str, Any]
def merge(a: Mapping[K, V], b: Mapping[K, V]) -> dict[K, V]:
    return {**a, **b}
```

---

## TypedDict for JSON-like Data

Replace `dict[str, Any]`:

```python
from typing import TypedDict, NotRequired

class UserConfig(TypedDict):
    name: str
    age: int
    email: NotRequired[str]

class ApiResponse(TypedDict):
    status: int
    data: list[UserConfig]
    error: NotRequired[str]

def parse_response(raw: object) -> ApiResponse:
    # Validate structure here
    ...
```

---

## Overload for Multiple Signatures

When return type depends on input:

```python
from typing import overload, Literal

@overload
def fetch(url: str, raw: Literal[True]) -> bytes: ...
@overload
def fetch(url: str, raw: Literal[False] = False) -> str: ...
@overload
def fetch(url: str, raw: bool = False) -> str | bytes: ...

def fetch(url: str, raw: bool = False) -> str | bytes:
    response = requests.get(url)
    return response.content if raw else response.text
```

---

## Type Aliases

Improve readability:

```python
from typing import TypeAlias

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonArray: TypeAlias = list["JsonValue"]
JsonObject: TypeAlias = dict[str, "JsonValue"]
JsonValue: TypeAlias = JsonPrimitive | JsonArray | JsonObject

# Now use JsonValue instead of Any
def parse_json(data: str) -> JsonValue:
    ...
```

---

## Common Replacements

| Instead of | Use |
|------------|-----|
| `Any` | Specific type, Union, Protocol |
| `dict[str, Any]` | TypedDict, Mapping[str, V] |
| `list[Any]` | list[T], Sequence[T] |
| `Callable[..., Any]` | Callable[P, R] with ParamSpec |
| `object` (for catch-all) | Protocol with required methods |
| `type[Any]` | type[T] with bound TypeVar |

---

## Self Type (Python 3.11+)

For methods returning the instance type:

```python
from typing import Self

class Builder:
    def with_name(self, name: str) -> Self:
        self._name = name
        return self  # Returns correct subclass type

    def with_value(self, value: int) -> Self:
        self._value = value
        return self

class ExtendedBuilder(Builder):
    def with_extra(self, extra: str) -> Self:
        self._extra = extra
        return self

# Type-safe chaining
b = ExtendedBuilder().with_name("x").with_extra("y")  # ExtendedBuilder
```

---

## TypeVarTuple (Python 3.11+)

For variadic generics:

```python
from typing import TypeVarTuple, Unpack

Ts = TypeVarTuple("Ts")

def first_of[*Ts](args: tuple[*Ts]) -> tuple[*Ts]:
    """Return the tuple unchanged - preserves all types."""
    return args

# Preserves exact tuple types
result = first_of((1, "a", True))  # tuple[int, str, bool]
```

---

## Unpack for TypedDict kwargs

Pass TypedDict as **kwargs with type safety:

```python
from typing import TypedDict, Unpack

class Options(TypedDict, total=False):
    timeout: int
    retries: int
    verbose: bool

def configure(**kwargs: Unpack[Options]) -> None:
    timeout = kwargs.get("timeout", 30)
    retries = kwargs.get("retries", 3)
    ...

# Type-checked kwargs
configure(timeout=60, retries=5)  # OK
configure(invalid=True)  # Error - not in Options
```

---

## Concatenate for Decorator Parameters

Add parameters to decorated functions:

```python
from typing import Concatenate, ParamSpec, TypeVar
from collections.abc import Callable

P = ParamSpec("P")
R = TypeVar("R")

def with_context(
    func: Callable[Concatenate[Context, P], R]
) -> Callable[P, R]:
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        ctx = get_context()
        return func(ctx, *args, **kwargs)
    return wrapper

@with_context
def process(ctx: Context, data: str) -> int:
    return ctx.handle(data)

# Called without ctx - decorator provides it
process("data")  # Type-safe
```

---

## NewType for Semantic Types

Create distinct types without runtime overhead:

```python
from typing import NewType

UserId = NewType("UserId", int)
OrderId = NewType("OrderId", int)

def get_user(user_id: UserId) -> User: ...
def get_order(order_id: OrderId) -> Order: ...

uid = UserId(123)
oid = OrderId(456)

get_user(uid)  # OK
get_user(oid)  # Error - OrderId is not UserId
get_user(123)  # Error - int is not UserId
```

---

## Annotated for Metadata

Attach validation metadata to types:

```python
from typing import Annotated
from dataclasses import dataclass

# Define constraints (runtime validation optional)
PositiveInt = Annotated[int, "positive"]
Email = Annotated[str, "email_format"]
NonEmpty = Annotated[str, "non_empty"]

@dataclass
class User:
    id: PositiveInt
    email: Email
    name: NonEmpty
```

---

## ClassVar and Final

For class-level and immutable types:

```python
from typing import ClassVar, Final

class Config:
    # Class variable, not instance
    default_timeout: ClassVar[int] = 30

    # Cannot be reassigned
    VERSION: Final[str] = "1.0.0"

    def __init__(self, timeout: int | None = None) -> None:
        self.timeout = timeout or Config.default_timeout

# Final variables
MAX_RETRIES: Final = 3  # Inferred as Final[int]
```

---

## Bound TypeVars

Constrain TypeVar to specific base types:

```python
from typing import TypeVar
from collections.abc import Sequence

# T must be a Sequence subtype
SeqT = TypeVar("SeqT", bound=Sequence[int])

def sum_sequence(seq: SeqT) -> int:
    return sum(seq)

sum_sequence([1, 2, 3])      # OK - list[int] is Sequence[int]
sum_sequence((1, 2, 3))      # OK - tuple is Sequence[int]
sum_sequence({1, 2, 3})      # Error - set is not Sequence

# Constrained to specific types (not subclasses)
StrOrBytes = TypeVar("StrOrBytes", str, bytes)

def process(data: StrOrBytes) -> StrOrBytes:
    return data  # Returns same type as input
```

---

## TypeGuard vs TypeIs (Python 3.13+)

```python
from typing import TypeGuard, TypeIs

# TypeGuard - narrows to the specified type (lossy)
def is_str_list(val: list[object]) -> TypeGuard[list[str]]:
    return all(isinstance(x, str) for x in val)

# TypeIs - preserves type relationship (Python 3.13+)
def is_str(val: object) -> TypeIs[str]:
    return isinstance(val, str)

def process(val: str | int) -> None:
    if is_str(val):
        # With TypeIs: val is str
        # With TypeGuard: val would be str (but less precise)
        print(val.upper())
```

---

## assert_type for Validation

Verify types during development:

```python
from typing import assert_type

def get_data() -> dict[str, int]:
    result = complex_operation()
    # Fails type check if result isn't dict[str, int]
    assert_type(result, dict[str, int])
    return result
```

---

## Never Type

For functions that never return:

```python
from typing import Never, NoReturn

def fail(message: str) -> Never:
    raise RuntimeError(message)

def infinite_loop() -> NoReturn:
    while True:
        pass

# Useful for exhaustiveness checking
def handle(value: str | int) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    # If we get here, type is Never (impossible)
    fail(f"Unexpected type: {type(value)}")
```

---

## LiteralString for Security

Prevent injection vulnerabilities:

```python
from typing import LiteralString

def execute_sql(query: LiteralString) -> list[Row]:
    # Only accepts literal strings, not user input
    return db.execute(query)

execute_sql("SELECT * FROM users")  # OK
execute_sql(f"SELECT * FROM {table}")  # Error - not literal
```

---

## Required and NotRequired in TypedDict

Fine-grained optionality:

```python
from typing import TypedDict, Required, NotRequired

class Config(TypedDict, total=False):
    # All optional by default due to total=False
    debug: bool
    verbose: bool
    # But name is required even with total=False
    name: Required[str]

class StrictConfig(TypedDict):
    # All required by default
    name: str
    version: str
    # But debug is optional
    debug: NotRequired[bool]
```

---

## ReadOnly TypedDict (Python 3.13+)

Immutable typed dictionaries:

```python
from typing import TypedDict, ReadOnly

class Config(TypedDict):
    name: ReadOnly[str]  # Cannot be modified
    value: int  # Can be modified

def process(config: Config) -> None:
    config["value"] = 10  # OK
    config["name"] = "new"  # Error - ReadOnly
```

---

## Generic Protocols

Protocols with type parameters:

```python
from typing import Protocol, TypeVar

T_co = TypeVar("T_co", covariant=True)

class Reader(Protocol[T_co]):
    def read(self) -> T_co: ...

class Writer(Protocol[T_co]):
    def write(self, data: T_co) -> None: ...

class FileReader:
    def read(self) -> bytes: ...

def process(reader: Reader[bytes]) -> bytes:
    return reader.read()

process(FileReader())  # OK - FileReader satisfies Reader[bytes]
```

---

## Covariance and Contravariance

```python
from typing import TypeVar

# Covariant - can use subtypes (output positions)
T_co = TypeVar("T_co", covariant=True)

# Contravariant - can use supertypes (input positions)
T_contra = TypeVar("T_contra", contravariant=True)

class Producer(Protocol[T_co]):
    def produce(self) -> T_co: ...

class Consumer(Protocol[T_contra]):
    def consume(self, item: T_contra) -> None: ...

# Producer[Dog] is subtype of Producer[Animal]
# Consumer[Animal] is subtype of Consumer[Dog]
```
