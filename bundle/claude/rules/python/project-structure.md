---
globs: **/*.py, **/pyproject.toml
---

# Python Project Structure

## Imports & privacy

- **Never import `_private` from other packages** — the underscore is a contract. Use the public API.
- Within a package, relative `_private` imports are fine (`from ._helpers import _build_query`).
- `__all__` defines the public surface.
- Multiple imports from one module → `from . import utils` then `utils.parse(...)`.
- **PY-IMPORT-002:** canonical aliases only (`np`, `pd`, project-established). Don't invent.

## Flat module vs package

**Flat `thing.py`** — under ~250 lines, one cohesive responsibility, no private helpers worth hiding.

**Package `thing/`** — approaching ~250 lines, has private helpers, has sub-responsibilities, or needs a clean public API.

## Preemptive split triggers (PY-CODE-017/018)

Do the split **before** the hook fires:

- Module at ~250 lines and growing → promote to package.
- Two `<prefix>_*.py` siblings exist, about to add a third → make `prefix/` package. The shared prefix IS the package name.
- Function at ~30 lines with another responsibility coming → extract.

Three flat siblings is the antipattern, not the warning shot.

## Package pattern

```
auth/
├── __init__.py      # public API re-exports only — no logic
├── _tokens.py
├── _passwords.py
└── _middleware.py
```

```python
# auth/__init__.py
from ._tokens import create_token, validate_token
from ._passwords import hash_password, check_password
__all__ = ["create_token", "validate_token", "hash_password", "check_password"]
```

Consumers: `from my_project.auth import create_token` — not `from my_project.auth._tokens import ...`.

## Avoid flat `_module` sprawl

3+ `_files` in one directory → split into sub-packages by responsibility. The hook will deny the 4th.

## Circular imports

- High-level imports low-level, never the reverse.
- `TYPE_CHECKING` guard for type-only imports that would cycle:
  ```python
  from typing import TYPE_CHECKING
  if TYPE_CHECKING:
      from .service import UserService
  ```
- If two modules need each other at runtime, they belong in the same package or need a Protocol between them.
