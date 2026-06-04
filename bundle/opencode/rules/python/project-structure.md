
# Python Project Structure

## Imports & Privacy

- **Never import `_private` names from other packages** — the underscore is a contract
  ```python
  # Bad — reaching into another package's internals
  from some_package._internal import _parse_token
  from some_package._helpers import _build_query

  # Good — use the public API
  from some_package import parse_token
  from some_package.helpers import build_query
  ```
- **Within a package**, relative imports of `_private` siblings are fine — that's the point:
  ```python
  # Inside my_package/service.py — OK
  from ._helpers import _build_query
  from ._config import _load_defaults
  ```
- **`__all__` defines the public surface** — if a module has `__all__`, only those names are public
- **Import the module, not the internals** when you need multiple things:
  ```python
  # Bad — 6 lines of imports from one module
  from utils import parse, validate, clean, format, transform, check

  # Good — import the module
  from . import utils
  result = utils.parse(data)
  ```
- `PY-IMPORT-002`: use canonical aliases only (`np`, `pd`, project-established shorthands). Do not invent nonstandard aliases for modules, classes, or helpers; import the real name unless the repo already standardizes the alias.

## When to Use a Flat Module vs a Package Directory

**Flat module** (`thing.py`) when:
- Under ~300 lines
- One cohesive responsibility
- No internal helpers worth hiding

**Package directory** (`thing/`) when:
- Over ~300 lines or growing
- Has private helpers that shouldn't be importable from outside
- Has distinct sub-responsibilities that deserve separate files
- Needs to hide complexity behind a clean `__init__.py` API

`PY-CODE-018` / `PY-CODE-017`: if the current module is over ~300 lines or adding a third `prefix_*.py` sibling, promote to a `prefix/` package with `__init__.py` re-exporting the public API. Do not create flat sibling sprawl.

## Package Directory Pattern

When a module outgrows a single file, promote it to a package:

```
# Before — one fat file
my_project/
├── auth.py              # 600 lines, growing

# After — contained package
my_project/
├── auth/
│   ├── __init__.py      # public API: re-exports only
│   ├── _tokens.py       # JWT creation/validation
│   ├── _passwords.py    # hashing, strength checks
│   ├── _oauth.py        # OAuth2 flow
│   └── _middleware.py    # request auth middleware
```

### The `__init__.py` Contract

```python
# auth/__init__.py — clean public API
from ._tokens import create_token, validate_token
from ._passwords import hash_password, check_password
from ._middleware import require_auth

__all__ = [
    "create_token",
    "validate_token",
    "hash_password",
    "check_password",
    "require_auth",
]
```

**Rules:**
- `__init__.py` re-exports the public API — no logic, no classes, no functions defined here
- Internal modules are prefixed with `_` — signals "don't import directly"
- **Consumers import from the package**, not from internal modules:
  ```python
  # Good — package-level import
  from my_project.auth import create_token

  # Bad — reaching into internals
  from my_project.auth._tokens import create_token
  ```

## Avoiding the Flat `_module` Antipattern

```
# Bad — flat folder of underscore modules with no containment
my_project/
├── _helpers.py
├── _utils.py
├── _config.py
├── _database.py
├── _models.py
├── _validators.py
├── _formatters.py
└── main.py        # imports from all of the above

# Good — grouped into packages by responsibility
my_project/
├── config/
│   ├── __init__.py
│   ├── _loader.py
│   └── _schema.py
├── database/
│   ├── __init__.py
│   ├── _connection.py
│   └── _models.py
├── validation/
│   ├── __init__.py
│   └── _rules.py
└── main.py
```

**Heuristic:** If you have 4+ `_files` in one directory, you probably need sub-packages.

## Circular Import Prevention

- **Imports flow downward**: high-level modules import low-level ones, never the reverse
- **TYPE_CHECKING guard** for type-only imports that would create cycles:
  ```python
  from __future__ import annotations
  from typing import TYPE_CHECKING

  if TYPE_CHECKING:
      from .service import UserService  # only for type hints
  ```
- If two modules need each other at runtime, they belong in the same package or need an interface/protocol between them
