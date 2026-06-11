# Refactoring Patterns

## Module-to-package split

Use for `PY-CODE-018`, oversized-module `QUALITY-LINT-001`, and files that have become multiple responsibilities in one module.

```text
# Before
src/app/services.py

# After
src/app/services/
  __init__.py      # public facade only
  users.py         # user service
  billing.py       # billing service
  notifications.py # notification service
  _shared.py       # private shared helpers, if truly shared
```

Facade example:

```python
from .billing import BillingService
from .notifications import NotificationService
from .users import UserService

__all__ = ["BillingService", "NotificationService", "UserService"]
```

Rules:

- Split by cohesive responsibility, not equal line counts.
- Keep public imports stable when feasible.
- Keep `__init__.py` thin; it must not become the old oversized file.
- Move tests or add focused tests for each extracted seam.
- **Preserve explanatory text.** Module docstrings, `# Why this exists` comments, blank lines between logical groups, and multi-line `try/except` bodies move with the code unchanged. A package split is a relocation, not a compression pass. If the split appears to require stripping comments or collapsing whitespace to "fit," the new module boundary is wrong — re-plan the seam.
- **Trigger preemptively.** Promote to a package at ~250 lines or when a second `<prefix>_*.py` sibling already exists, not when the file is at 600 and a hook denies the next write.

## Flat sibling cluster to package

Use for `PY-CODE-017`. **Trigger when the second `<prefix>_*.py` sibling already exists** — the third file is the antipattern, not the warning shot.

```text
# Before — already a smell at two siblings, blocked at three
src/agents/result_models.py
src/agents/result_runner.py
src/agents/result_reconciliation.py   # ← do not write this; do the split first

# After
src/agents/result/
  __init__.py
  models.py
  runner.py
  reconciliation.py
```

Checklist:

1. Create package directory.
2. Move existing sibling content into cohesive package modules **with their docstrings, comments, and blank-line groupings intact**. Do not collapse `try/except` blocks, do not strip module headers, do not reformat for line-count gains.
3. Add facade re-exports for public names.
4. Update imports:
   - external callers: `from agents.result import ResultRunner`;
   - internal package modules: `from .models import ResultModel`.
5. Remove old flat sibling files in the same repair.
6. Compile and run focused import/tests.

### Worked positive example

`cloud/services/event_buffer/` is a clean reference: `_buffer.py`, `_archive.py`, `_models.py`, `_snapshot.py`, `_lifecycle.py`, `_replay.py`, `_waiters.py`, `_constants.py` under one package, each underscore-prefixed sibling owns one responsibility, `__init__.py` re-exports the public API, no flat `event_buffer_*.py` siblings exist outside the package. Use this as the canonical shape when promoting a new package.

## Blast-radius checklist before any split

Run before moving a single line. The full command set lives in `code-hygiene-refactor/SKILL.md` under "Blast-radius measurement." Minimum:

1. **GitNexus** (preferred): `gitnexus_impact({target, direction: "upstream"})` + `gitnexus_context({name})`. If stale → `npx gitnexus analyze` first.
2. **Fallback** when GitNexus is unavailable:
   - `rg -n --pcre2 "^\s*(from\s+<MODULE>\s+import|import\s+<MODULE>)" -t py` — direct importers
   - `rg -nw "<SYMBOL>" -t py` — symbol mentions
   - `rg -l "<SYMBOL>" tests/` — test coverage of the symbol
   - `git log --pretty=format: --name-only --diff-filter=AM -- <file> | sort | uniq -c | sort -rn | head` — co-change history (files that always change together belong in the same package)
   - `wc -l <file>` and `rg -n "^(def|class|async def) " <file> | wc -l` — size and surface count

Treat the union of (1) direct importers and (3) test files as the authoritative caller set. Anything imported only inside the same package is safe to move; anything imported from elsewhere either keeps its name through the new `__init__.py` facade or gets an explicit migration edit in the same PR.

## Long method extraction

- Extract named steps that match domain actions.
- Prefer guard clauses over nested conditionals.
- Keep extracted helpers close to their owner unless reused across domains.
- Do not create a generic helper just to hide complexity.

## God class extraction

**Threshold:** `PY-CODE-014` denies at >10 non-dunder methods. The preemptive trigger is **8 methods + an obvious 9th coming in this PR**, not 11 with the hook in your face.

### Preemptive triggers (do this before the hook fires)

- 8 non-dunder methods and the current edit adds the 9th or 10th.
- Class crossed ~250 lines even if method count is fine — class-line and method-count budgets converge.
- Two or more visible domain concerns (e.g. "manages state" + "writes archive" + "schedules cleanup") owned by the same class.
- Tests have started clustering by method group (`TestUserAuth` + `TestUserProfile` for one `User`) — production has already split conceptually; finish the split structurally.
- A new method needs 3+ existing instance attributes that no other method touches → that method belongs on the collaborator that owns those attributes, not on the parent.

### Extraction recipe

1. **Identify the seam.** Group methods by the data they mutate and the collaborators they call. A clean seam is a set of methods that share state with each other and barely touch anything else on the class.
2. **Name the collaborator after the responsibility, not the class.** `RunArchiveStore`, not `EventBufferArchiveHelper`. The new class should read as a domain noun.
3. **Constructor injection, no module globals.** The new collaborator gets its dependencies through `__init__` parameters. The parent class instantiates it once and forwards calls — or, better, exposes the collaborator as a public attribute when callers can use it directly.
4. **Move the tests with the methods.** If `TestUserAuth` covered the extracted methods, it follows the methods to `tests/.../test_auth_collaborator.py`. Do not leave orphaned test classes referencing methods that no longer exist on the parent.
5. **Add a characterization test before the move** if the behavior under extraction is non-trivial — a single high-level test that exercises the parent's public API end-to-end. After extraction, that test should still pass unchanged.
6. **Keep the parent only as a real facade.** If after extraction the parent class is just `__init__` plus four delegating one-liners, inline its remaining behavior into the call site or rename the collaborator to take its place. A thin orchestrator that owns no state and delegates everything is `PY-CODE-013` waiting to fire.

### Worked positive example

`cloud/services/event_buffer/_buffer.py`'s `EventBuffer` was split when it crossed the method-count budget: lifecycle helpers moved to `_lifecycle.py` as module-level functions over a `BufferState` dataclass; archive I/O moved to `RunArchiveStore` in `_archive.py`; snapshot persistence moved to `_snapshot.py`. The remaining `EventBuffer` keeps exactly the public methods callers use (`claim_run`, `append`, `replay_from`, `cleanup`, etc.) — no stub orchestration methods, no facade-as-god-class regression. That is the target shape.

### Anti-patterns to refuse

- **Random method shuffling to get under 10.** Splitting a class by alphabetizing methods and moving the back half is not refactoring; it is hiding the smell.
- **`Helper` / `Manager` / `Service` suffix on the new class without a domain noun.** If you cannot name the responsibility, you have not found the seam.
- **Moving a method but keeping a one-line wrapper on the parent that calls it.** That trips `PY-CODE-013` on the next pass. Either move the callers too or keep the method on the parent.
- **Extracting a collaborator that needs the parent passed into its `__init__`.** Bidirectional dependency = the seam was wrong; re-plan.

## Thin wrapper recovery

A wrapper is acceptable only when it adds semantic value:

- validation;
- normalization;
- caching;
- error translation;
- tracing/metrics policy;
- stable public facade over volatile internals.

Otherwise inline it or move the call to the true owner.

## Feature envy recovery

If a function repeatedly pulls fields/methods from another object, move the behavior to that object or create a domain method there. Avoid passing many fields as a parameter bag.

## Duplicate helper / repeated literal recovery

1. Search existing helpers/constants first.
2. If Slopgate cites an existing constant, read the cited owner (`path:line`), confirm semantic fit, import that symbol, and replace the duplicate literal with the import.
3. If none exists, choose the narrowest domain owner.
4. Avoid `utils.py` dumping grounds.
5. Preserve protocol/schema keys where literal extraction would make code less clear; only extract semantic repeated values.
6. Reject detector camouflage: no string fragmentation (`"pri" + "mary"`), partial-constant stitching (`PK_PRI + "mary"`), alias-only constants, tuple/list packing, or generated indirection whose only purpose is to change hashes.

## Test and fixture bloat recovery

- Split tests by behavior under test.
- Prefer parameterization over loops with assertions.
- Keep area `conftest.py` thin; import fixture implementations from `_fixtures/` or `support/` when project policy allows.
- Do not hide fixture complexity in a giant shared conftest.
