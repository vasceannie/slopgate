# Third-Party Library Typing Strategies

Techniques for typing code that uses untyped or partially typed third-party libraries.

---

## Strategy Overview

```
┌────────────────────────────────────────────────────────────────┐
│  1. CHECK FOR EXISTING STUBS                                   │
│     PyPI: types-{pkg}, {pkg}-stubs                             │
│     Typeshed: github.com/python/typeshed                       │
├────────────────────────────────────────────────────────────────┤
│  2. INSPECT LIBRARY SOURCE                                     │
│     Read actual signatures from installed package              │
│     Check for inline py.typed marker                           │
├────────────────────────────────────────────────────────────────┤
│  3. CREATE LOCAL STUBS                                         │
│     Write .pyi files for used portions only                    │
│     Configure stubPath in pyproject.toml                       │
├────────────────────────────────────────────────────────────────┤
│  4. USE PROTOCOL WRAPPERS                                      │
│     Define Protocols matching library interfaces               │
│     Type against Protocol, not library types                   │
├────────────────────────────────────────────────────────────────┤
│  5. WRAPPER MODULES                                            │
│     Create typed wrappers around untyped APIs                  │
│     Contain untyped code in single location                    │
└────────────────────────────────────────────────────────────────┘
```

---

## Inspecting Library Source

Find type information from installed packages:

```bash
# Locate package
python3 -c "import package; print(package.__file__)"

# Check for py.typed marker
python3 -c "
import pathlib
import package
pkg_dir = pathlib.Path(package.__file__).parent
print('Typed:', (pkg_dir / 'py.typed').exists())
"

# Get function signature
python3 -c "import package; help(package.function)"

# Inspect with inspect module
python3 -c "
import inspect
import package
sig = inspect.signature(package.function)
print(sig)
for name, param in sig.parameters.items():
    print(f'  {name}: {param.annotation}')
print(f'  return: {sig.return_annotation}')
"
```

---

## Creating Local Stubs

### Directory Structure

```
project/
├── src/
│   └── myapp/
├── _stubs/
│   ├── untyped_lib/
│   │   ├── __init__.pyi
│   │   └── submodule.pyi
│   └── another_lib.pyi
└── pyproject.toml
```

### Stub File Syntax

```python
# _stubs/untyped_lib/__init__.pyi
from typing import overload

# Module-level variables
VERSION: str
DEBUG: bool

# Functions
def process(data: bytes) -> str: ...

@overload
def fetch(url: str, raw: True) -> bytes: ...
@overload
def fetch(url: str, raw: False = ...) -> str: ...

# Classes
class Client:
    timeout: int

    def __init__(self, base_url: str, timeout: int = ...) -> None: ...
    def get(self, path: str) -> bytes: ...
    def post(self, path: str, data: dict[str, str]) -> bytes: ...

    @property
    def is_connected(self) -> bool: ...
```

### Configuration

```toml
# pyproject.toml

[tool.pyright]
stubPath = "_stubs"

[tool.mypy]
mypy_path = "_stubs"
```

---

## Protocol Wrappers

When library types are too complex, define Protocols:

```python
# protocols.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class DatabaseConnection(Protocol):
    """Protocol for database connections."""

    def execute(self, query: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...

@runtime_checkable
class HttpClient(Protocol):
    """Protocol for HTTP clients."""

    def get(self, url: str, **kwargs: object) -> "Response": ...
    def post(self, url: str, data: bytes, **kwargs: object) -> "Response": ...

class Response(Protocol):
    status_code: int
    content: bytes

    def json(self) -> dict[str, object]: ...

# Usage - type against Protocol, not library type
def save_data(conn: DatabaseConnection, data: dict[str, str]) -> None:
    conn.execute("INSERT ...", tuple(data.values()))
    conn.commit()
```

---

## Typed Wrapper Modules

Contain untyped code in dedicated modules:

```python
# adapters/http_client.py
"""Typed wrapper for untyped HTTP library."""

from typing import TypedDict
from untyped_http_lib import Client as _UntypedClient  # Internal import

class RequestOptions(TypedDict, total=False):
    timeout: int
    headers: dict[str, str]
    verify_ssl: bool

class Response:
    """Typed response wrapper."""

    def __init__(self, raw_response: object) -> None:
        self._raw = raw_response

    @property
    def status_code(self) -> int:
        code = getattr(self._raw, "status_code", None)
        if not isinstance(code, int):
            raise TypeError("Invalid status code")
        return code

    @property
    def content(self) -> bytes:
        content = getattr(self._raw, "content", b"")
        if not isinstance(content, bytes):
            raise TypeError("Invalid content")
        return content

    def json(self) -> dict[str, object]:
        data = getattr(self._raw, "json", lambda: {})()
        if not isinstance(data, dict):
            raise TypeError("Invalid JSON response")
        return data

class HttpClient:
    """Typed HTTP client wrapping untyped library."""

    def __init__(self, base_url: str, **options: object) -> None:
        self._client = _UntypedClient(base_url, **options)

    def get(self, path: str, **options: object) -> Response:
        raw = self._client.get(path, **options)
        return Response(raw)

    def post(self, path: str, data: bytes, **options: object) -> Response:
        raw = self._client.post(path, data=data, **options)
        return Response(raw)
```

---

## TypedDict for Library Config

Replace `dict[str, Any]` config patterns:

```python
from typing import TypedDict, NotRequired

# Instead of passing dict[str, Any] to library
class DatabaseConfig(TypedDict):
    host: str
    port: int
    database: str
    user: NotRequired[str]
    password: NotRequired[str]
    ssl: NotRequired[bool]

def create_connection(config: DatabaseConfig) -> Connection:
    # Library accepts **kwargs or dict
    return untyped_lib.connect(**config)
```

---

## Handling Dynamic Returns

When library returns vary by input:

```python
from typing import TypeVar, overload, Literal

T = TypeVar("T")

# Library has: def get(key, default=None) -> ???

# Create typed wrapper
@overload
def typed_get(key: str) -> str | None: ...
@overload
def typed_get(key: str, default: T) -> str | T: ...

def typed_get(key: str, default: T | None = None) -> str | T | None:
    result = untyped_cache.get(key, default)
    if result is not None and not isinstance(result, str):
        if default is not None:
            return default
        return None
    return result
```

---

## Callback Typing

Type callbacks passed to untyped libraries:

```python
from collections.abc import Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

# Define expected callback signature
EventHandler = Callable[[str, dict[str, object]], None]
ErrorCallback = Callable[[Exception], None]

def register_handler(event: str, handler: EventHandler) -> None:
    # Library accepts callable with unknown signature
    untyped_lib.on(event, handler)

# Usage with type safety
def my_handler(event_name: str, data: dict[str, object]) -> None:
    print(f"Got {event_name}: {data}")

register_handler("user.created", my_handler)  # Type-checked
```

---

## Factory Pattern for Library Objects

Create typed factories for library instantiation:

```python
from typing import Protocol

class Logger(Protocol):
    def info(self, msg: str) -> None: ...
    def error(self, msg: str, exc: Exception | None = None) -> None: ...
    def debug(self, msg: str) -> None: ...

def create_logger(name: str, level: str = "INFO") -> Logger:
    """Create typed logger from untyped library."""
    raw_logger = untyped_logging.get_logger(name)
    raw_logger.setLevel(level)
    # raw_logger satisfies Logger protocol
    return raw_logger  # type: ignore[return-value] - ONLY if truly unavoidable
```

**Note**: If cast or ignore is needed at the boundary, document why and keep it contained.

---

## Validation Functions

Type-validate data from untyped sources:

```python
from typing import TypeGuard, TypedDict

class UserData(TypedDict):
    id: int
    name: str
    email: str

def is_user_data(data: object) -> TypeGuard[UserData]:
    """Validate data matches UserData structure."""
    if not isinstance(data, dict):
        return False
    return (
        isinstance(data.get("id"), int)
        and isinstance(data.get("name"), str)
        and isinstance(data.get("email"), str)
    )

def fetch_user(user_id: int) -> UserData:
    """Fetch and validate user data from untyped API."""
    raw = untyped_api.get(f"/users/{user_id}")
    if not is_user_data(raw):
        raise ValueError(f"Invalid user data: {raw}")
    return raw
```

---

## Partial Stubs

Stub only what you use:

```python
# _stubs/large_library/__init__.pyi
# Only stub the parts actually imported

from typing import overload

# We only use these functions
def used_function(x: str) -> int: ...
def another_used(data: bytes) -> str: ...

# We only use these classes
class UsedClass:
    def __init__(self, config: dict[str, str]) -> None: ...
    def process(self) -> bytes: ...

# Everything else is intentionally omitted
# Pyright will still warn if you use unstubbed parts
```

---

## Common Library Patterns

### SQLAlchemy (2.0+ is typed)

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

def get_user(session: Session, user_id: int) -> User | None:
    stmt = select(User).where(User.id == user_id)
    return session.scalar(stmt)
```

### Pydantic (fully typed)

```python
from pydantic import BaseModel

class Config(BaseModel):
    host: str
    port: int
    debug: bool = False

config = Config(host="localhost", port=8080)  # Type-safe
```

### Requests (use types-requests)

```python
# pip install types-requests
import requests

def fetch_json(url: str) -> dict[str, object]:
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise TypeError("Expected JSON object")
    return data
```

### Boto3 (use boto3-stubs)

```python
# pip install "boto3-stubs[s3]"
import boto3
from mypy_boto3_s3 import S3Client

def get_s3_client() -> S3Client:
    return boto3.client("s3")

def list_buckets(client: S3Client) -> list[str]:
    response = client.list_buckets()
    return [b["Name"] for b in response.get("Buckets", [])]
```

---

## Troubleshooting

### Library has types but Pyright doesn't see them

Check for py.typed marker and package structure:

```bash
# Verify package is typed
python3 -c "
from importlib.metadata import files
pkg_files = files('package_name')
py_typed = any('py.typed' in str(f) for f in pkg_files)
print(f'Has py.typed: {py_typed}')
"
```

### Stubs installed but not recognized

```toml
# pyproject.toml - ensure stubs are in environment
[project.optional-dependencies]
dev = [
    "types-requests",
    "boto3-stubs[s3,dynamodb]",
]
```

### Conflicting stub versions

```bash
# Check installed stub versions
pip list | grep types-
pip list | grep stubs

# Pin compatible versions
pip install "types-requests>=2.31,<2.32"
```
