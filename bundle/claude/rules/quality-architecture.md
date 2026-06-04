# Architecture & Quality

## Structure

- **Single responsibility** per function/module.
- **Composition over inheritance** — inject collaborators.
- **Functional core / imperative shell** — pure logic returns values, I/O at boundaries.
- **Dependency injection** — pass deps as params, avoid module singletons/globals.
- **Events/callbacks/protocols** between loosely coupled modules.

## Resist over-abstraction

- Don't extract unless reused or genuinely complex.
- Inline 5-line blocks beat indirection through `_do_thing()`.
- Single-call-site functions are gotos with extra steps (PY-CODE-013).
- Before extracting: "Would a reader understand faster with or without this?"

## Flat > nested

Guard clauses + early returns over nested if/else.

```python
def process(data):
    if not data: return None
    if not data.valid: return None
    if not data.ready: return None
    return transform(data)
```

## Naming

- Functions: verbs (`calculate_total`, `fetch_user`).
- Classes: nouns (`UserRepository`).
- Booleans: questions (`is_valid`, `has_permission`).
- Constants: meaning, not value (`MAX_RETRY_ATTEMPTS = 3`).

## Separation

- Config separate from logic — load at startup, pass values down.
- Validate at boundaries; trust internally.
- Handle errors at the appropriate level — don't catch and re-raise without adding context.

## Boundary observability (PY-LOG-002)

- Boundary crossings → structured logger/telemetry, not `print()`/raw dumps.
- Log operation name, direction/status, and correlation/request ID when available.
- Keep payloads safe: never log raw payloads, secrets, auth headers, cookies, tokens, or credential-bearing exception text.
- If denied, identify the boundary type first (adapter/client/gateway/event handler), then add the smallest project-standard breadcrumb and focused boundary test.

## Hook-anchored repairs

- `PY-CODE-013` thin wrappers: inline unless wrapper names a real concept, enforces a boundary, or centralizes policy.
- `PY-CODE-017` flat sibling sprawl: create a named sub-package, not many shared-prefix files.
- `PY-CODE-018` oversized modules: cohesive package/service split, preserve public imports via `__init__.py`.
- `PY-CODE-014` god class: extract collaborators by responsibility (data mutated + collaborators called).
- `PY-IMPORT-003` stacked private import chains: expose a package facade or use descriptive public submodules; avoid `pkg._impl._core` paths.
- `PY-QUALITY-009` hardcoded paths: use config, pathlib helpers, or project constants instead of local machine paths; do not turn URL routes into fake path constants.
- `PY-QUALITY-010` magic numbers/repeated semantic literals: create named constants; do not split strings/numbers to dodge detection.
- `PY-AST-001` syntax/read failure: repair parseability first.
