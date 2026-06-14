---
name: type-strictness
description: |
  Enforce strict type compliance by eliminating `Any` types and `# type: ignore` comments. Use when:
  (1) Editing code that contains `Any` as a type annotation
  (2) Code has `# type: ignore` or `# pyright: ignore` comments
  (3) User requests type fixes or type strictness enforcement
  (4) Importing from untyped third-party libraries
  (5) User asks to "fix types", "remove Any", or "add proper typing"
  (6) Pyrefly or mypy reports type errors that need resolution
  (7) Code review reveals weak typing patterns
  Follows hierarchical resolution: codebase inference → type stubs → library inspection → type guards → casting (last resort).
---

# Type Strictness

Eliminate `Any` types and type suppression comments through systematic resolution.

## Core Principle

**Never suppress type errors. Always fix them.**

The type system exists to catch bugs. Suppressing errors with `Any`, `# type: ignore`, or linter config changes defeats this purpose and hides real issues that will manifest as runtime bugs.

## Resolution Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│  1. INFER FROM CODEBASE                                         │
│     Search for existing type definitions, protocols, base       │
│     classes. Use find_symbol, find_referencing_symbols.         │
├─────────────────────────────────────────────────────────────────┤
│  2. FIND TYPE STUBS                                             │
│     Search PyPI for types-{package} or {package}-stubs.         │
│     Check typeshed for stdlib/popular package coverage.         │
├─────────────────────────────────────────────────────────────────┤
│  3. INSPECT LIBRARY SOURCE                                      │
│     Read library source for method signatures, return types.    │
│     Use site-packages inspection or GitHub source.              │
├─────────────────────────────────────────────────────────────────┤
│  4. TYPE GUARDS & NARROWING                                     │
│     Use TypeGuard, isinstance, hasattr checks.                  │
│     See references/resolution-patterns.md                       │
├─────────────────────────────────────────────────────────────────┤
│  5. CASTING (LAST RESORT)                                       │
│     Only when all above fail and type is provably correct.      │
│     Document why cast is necessary.                             │
└─────────────────────────────────────────────────────────────────┘
```

## Forbidden Patterns

| Pattern | Why Forbidden | Action |
|---------|---------------|--------|
| `Any` | Disables type checking | Resolve through hierarchy |
| `# type: ignore` | Hides real issues | Fix underlying error |
| `# type: ignore[code]` | Still suppresses | Fix the specific issue |
| `# pyright: ignore` | Same as above | Fix underlying error |
| `# noqa` (for type errors) | Circumvents linting | Address the actual issue |
| `object` as catch-all | Poor typing | Use Protocol or Union |
| Modifying strictness config | Weakens entire codebase | Fix issues individually |
| `cast(Any, x)` | Undermines type system | Use specific cast type |
| `-> None  # type: ignore` | Lying about return | Fix return annotation |

## Also Forbidden

- Changing `strict = true` to `false` in pyproject.toml
- Disabling specific pyright rules in config
- Adding packages to mypy's `ignore_missing_imports`
- Using `--no-strict-optional` or similar flags

## Phase 1: Detect Issues

Run type checker to identify issues:

```bash
# Pyrefly (preferred)
pyrefly check src/ --output-format json 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
for e in d.get('errors', []):
    print(f\"{e['path']}:{e['line']}:{e['column']} [{e['severity']}] {e['name']} - {e['concise_description']}\")
"

# Mypy alternative
mypy src/ --show-error-codes 2>&1 | grep -E "(Any|type: ignore)"
```

Search for violations:

```bash
# Find Any types
grep -rn ":\s*Any" --include="*.py" src/
grep -rn "-> Any" --include="*.py" src/
grep -rn "list\[Any\]" --include="*.py" src/

# Find type ignores
grep -rn "# type: ignore" --include="*.py" src/
grep -rn "# pyright: ignore" --include="*.py" src/
```

## Phase 2: Resolve Types

### Step 1: Codebase Inference

Search for existing definitions:

```python
# Find where the type is actually defined
find_symbol(name_path_pattern="ClassName", include_body=True)

# Find how it's used elsewhere (reveals expected type)
find_referencing_symbols(name_path="function_name", relative_path="module.py")

# Search for protocol definitions
search_for_pattern(
    substring_pattern="class.*Protocol",
    paths_include_glob="**/domain/**/*.py"
)
```

### Step 2: Find Type Stubs

Common stub packages:

| Library | Stub Package |
|---------|--------------|
| requests | `types-requests` |
| redis | `types-redis` |
| PyYAML | `types-PyYAML` |
| python-dateutil | `types-python-dateutil` |
| Pillow | `types-Pillow` |
| boto3 | `boto3-stubs` |
| SQLAlchemy | Built-in (2.0+) |

Check availability:

```bash
# Search PyPI for stubs
pip index versions types-{package} 2>/dev/null
pip index versions {package}-stubs 2>/dev/null
```

For complete list: See `references/common-stubs.md`

### Step 3: Library Inspection

Inspect installed package:

```bash
# Find package location
python3 -c "import {package}; print({package}.__file__)"

# Read source for signatures
python3 -c "import {package}; help({package}.{function})"
```

### Step 4: Type Guards & Narrowing

See `references/resolution-patterns.md` for:
- TypeGuard functions
- isinstance narrowing
- hasattr checks
- Protocol definitions
- Overload patterns

### Step 5: Casting (Last Resort)

Only if:
- All resolution steps exhausted
- Type is provably correct at runtime
- Documented with justification

```python
from typing import cast

# BAD: unexplained cast
value = cast(str, unknown_value)

# ACCEPTABLE: documented necessity
# cast required: third-party lib returns untyped dict but structure is documented
config = cast(dict[str, int], load_config())
```

## Tool Usage

| Tool | Purpose |
|------|---------|
| `pyrefly check` / `mypy` | Identify type errors |
| `find_symbol` | Find existing type definitions |
| `find_referencing_symbols` | Infer types from usage |
| `search_for_pattern` | Find Protocol/TypeVar patterns |
| `pip index versions` | Check for type stubs |
| `python -c "help(...)"` | Inspect library signatures |

## Output Checklist

After fixing, verify:

- [ ] No `Any` types remain (except in unavoidable edge cases with documentation)
- [ ] No `# type: ignore` comments
- [ ] No `# pyright: ignore` comments
- [ ] No linter config modifications that weaken type checking
- [ ] Type checker passes: `pyrefly check src/`
- [ ] If cast used, justification comment present
- [ ] Stubs installed for all third-party imports

## Reference Documents

| Reference | Contents |
|-----------|----------|
| `references/error-code-fixes.md` | Pyrefly/Mypy error codes with specific fix strategies |
| `references/resolution-patterns.md` | Advanced typing patterns: TypeGuard, Protocol, TypeVarTuple, Self, etc. |
| `references/common-stubs.md` | Type stub packages for popular libraries |
| `references/third-party-typing.md` | Strategies for typing untyped library code |

## Quick Decision Tree

```
Got a type error?
│
├─ Is it "Unknown type" or missing annotation?
│  └─ Add explicit type annotation at source
│
├─ Is it from third-party library?
│  ├─ Check for types-{pkg} stubs → Install
│  ├─ Check for {pkg}-stubs → Install
│  ├─ Library has py.typed? → Already typed, check version
│  └─ No stubs? → Create local .pyi stub (see third-party-typing.md)
│
├─ Is it a return type mismatch?
│  ├─ Function can return None? → Add `| None` to return type
│  ├─ Missing return path? → Add the return statement
│  └─ Wrong type returned? → Fix the return value
│
├─ Is it an argument type mismatch?
│  ├─ Can widen parameter? → Use Union or Protocol
│  ├─ Call site wrong? → Fix the call site
│  └─ Need overloads? → Add @overload signatures
│
├─ Is it Optional/None access?
│  ├─ Add None check before access
│  ├─ Use early return pattern
│  └─ Use walrus operator for assignment+check
│
└─ Complex dynamic type?
   ├─ Create TypedDict for dict structures
   ├─ Create Protocol for duck typing
   ├─ Use TypeGuard for runtime checks
   └─ See resolution-patterns.md for advanced patterns
```

## Common Scenarios

### JSON Data

```python
# BAD
def parse(data: str) -> dict[str, Any]:
    return json.loads(data)

# GOOD
class UserData(TypedDict):
    id: int
    name: str

def parse(data: str) -> UserData:
    result = json.loads(data)
    # Validate structure
    if not is_user_data(result):
        raise ValueError("Invalid data")
    return result
```

### Callback Functions

```python
# BAD
def register(callback: Callable[..., Any]) -> None: ...

# GOOD
from typing import ParamSpec, TypeVar
P = ParamSpec("P")
R = TypeVar("R")

def register(callback: Callable[P, R]) -> Callable[P, R]: ...
```

### Dictionary Access

```python
# BAD
config: dict[str, Any] = load_config()
timeout = config["timeout"]  # Unknown type

# GOOD
class Config(TypedDict):
    timeout: int
    retries: int

config: Config = load_config()
timeout = config["timeout"]  # int
```

### Optional Chaining

```python
# BAD (suppresses error)
user: User | None = get_user()
name = user.name  # type: ignore

# GOOD
user: User | None = get_user()
if user is not None:
    name = user.name
# OR
name = user.name if user else "Unknown"
```

## Modern Python Features (3.10+)

Prefer modern syntax for cleaner types:

| Old Style | Modern Style |
|-----------|--------------|
| `Optional[str]` | `str \| None` |
| `Union[int, str]` | `int \| str` |
| `List[str]` | `list[str]` |
| `Dict[str, int]` | `dict[str, int]` |
| `Tuple[int, ...]` | `tuple[int, ...]` |
| `Type[T]` | `type[T]` |

## When You're Truly Stuck

If after exhausting all options a type truly cannot be resolved:

1. **Isolate it**: Create a wrapper function/module that contains the untyped code
2. **Document it**: Add a detailed comment explaining why typing isn't possible
3. **Minimize scope**: Use the most specific type possible, not `Any`
4. **Open an issue**: If it's a library bug, report it upstream

Example of acceptable containment:

```python
# _untyped_wrappers.py
"""Wrappers for genuinely untyped library code.

Each wrapper isolates untyped library calls and provides typed interfaces.
Document why each is necessary.
"""

def get_legacy_config() -> dict[str, str]:
    """Wrap legacy_lib.config() which has no types and no stubs.

    Library is unmaintained (last update 2019) and we're migrating away.
    The return type is validated at runtime.
    """
    from legacy_lib import config  # Untyped import contained here
    result = config()
    if not isinstance(result, dict):
        raise TypeError("Unexpected config type")
    return {str(k): str(v) for k, v in result.items()}
```
