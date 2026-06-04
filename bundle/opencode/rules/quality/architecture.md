# Architecture & Code Quality

## Structure

- **Single Responsibility**: Each function does one thing; each module owns one domain
- **Composition > Inheritance**: "Has-a" over deep "is-a" hierarchies — inject collaborators, don't inherit them
- **Functional Core / Imperative Shell**: Pure business logic returns values; I/O and side effects live at the boundaries
- **Dependency Injection**: Pass dependencies as parameters — avoid module-level singletons and global state
- **Decoupling**: Use events, callbacks, or protocols between loosely coupled modules

## Resist Over-Abstraction

- Do not extract helpers unless the code is **reused or genuinely complex**
- Inline 5-line blocks are clearer than indirection through `_do_thing()`
- A function called from one place is just a goto with extra steps (PY-CODE-013 thin-wrapper risk)
- **Before extracting, ask**: "Would a reader understand this faster with or without the extraction?"

## Flat > Nested

- Prefer early returns and guard clauses over deeply nested if/else
- Flatten control flow before reaching for extraction:
  ```python
  # Bad — deep nesting
  def process(data):
      if data:
          if data.valid:
              if data.ready:
                  return transform(data)
      return None

  # Good — guard clauses
  def process(data):
      if not data:
          return None
      if not data.valid:
          return None
      if not data.ready:
          return None
      return transform(data)
  ```

## Naming

- Functions: verb phrases (`calculate_total`, `validate_input`, `fetch_user`)
- Classes: noun phrases (`UserRepository`, `PaymentProcessor`, `TokenValidator`)
- Booleans: question form (`is_valid`, `has_permission`, `should_retry`)
- Constants: describe the meaning, not the value (`MAX_RETRY_ATTEMPTS = 3`, not `THREE = 3`)

## Separation of Concerns

- **Configuration** separate from logic — load config at startup, pass values down
- **Data validation** at the boundary — validate once on entry, trust internally
- **Error handling** at the appropriate level — don't catch and re-raise without adding context

## Boundary Observability

- Boundary crossings need a structured project logger/telemetry breadcrumb, not `print()` or raw dumps.
- Log the operation/event name, direction or status, and correlation/request ID when one is available.
- Keep payloads safe: never log raw payloads, secrets, auth headers, cookies, tokens, or credential-bearing exception text.
- If denied by `PY-LOG-002`, identify the boundary type first (adapter/client/gateway/event handler), then add the smallest project-standard breadcrumb and focused boundary test.

## Why

Vibeforcer AST rules block deep nesting (>4 levels), long methods (>50 lines), thin wrappers, feature envy, and high cyclomatic complexity (>12). This rule teaches the design patterns that naturally stay within those limits.

## Hook-Anchored Architecture Repairs

- `PY-CODE-013`: thin wrappers are blocked. Inline trivial pass-throughs unless the wrapper names a real domain concept, enforces a boundary, or centralizes policy.
- `PY-CODE-017`: when splitting large modules, create a named sub-package instead of many flat files with a shared prefix.
- `PY-CODE-018`: oversized modules need a cohesive package/service split before adding more behavior; preserve public imports via `__init__.py` re-exports.
- `PY-CODE-014`: god classes need collaborator extraction by responsibility, not random method shuffling.
- `PY-IMPORT-003`: stacked private import chains need a public package facade or descriptive public submodule, not `pkg._impl._core` paths.
- `PY-QUALITY-009`: hardcoded filesystem paths belong in config/pathlib helpers/project constants; do not turn URL routes into fake path constants.
- `PY-QUALITY-010`: magic numbers/repeated semantic literals need named constants, not split strings/numbers that dodge detection.
- `PY-AST-001`: syntax/read failures outrank architecture; repair parseability before refactoring.
- `PY-LOG-002`: event publishers/handlers, adapters, clients, gateways, and other boundary code need structured project logging/telemetry with operation, direction/status, and safe correlation context.
