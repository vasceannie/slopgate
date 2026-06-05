---
name: code-hygiene-refactor
description: |
  Recovery playbook for Slopgate and project quality failures. Load after hook/lint denials such as PY-CODE-017 flat sibling modules, PY-CODE-018 oversized modules, QUALITY-LINT-001 post-edit quality backstops, PY-CODE-012/PY-CODE-013 smell findings, type-suppression bans, duplicate helpers, or repeated hygiene retry loops. Focuses on preserving public APIs while refactoring toward packages, cohesive modules, typed seams, and focused tests.
---

# Code Hygiene Refactor

Use this skill when a hook, linter, review, or CI gate says the code shape is wrong and the next move should be a refactor rather than another local patch. The goal is to fix the design signal without weakening the guardrail that caught it.

## Non-negotiables

1. **Do not weaken gates**: do not edit quality tests, rule configs, baselines, allowlists, thresholds, suppressions, or hook settings just to pass.
2. **No scoped fake-success lint**: public `slopgate lint check` is repo-root/full-scope only. Run it from the repo root; do not pass a file/path argument.
3. **No type suppression escapes**: avoid `# type: ignore`, `# pyright: ignore`, `# ty: ignore`, broad `Any`, and casts unless the project explicitly documents the exception.
4. **Repair before continuing**: if a PostToolUse/after-edit backstop blocked, assume the bad mutation has landed. Fix it before unrelated edits.
5. **Preserve public API**: package splits should keep import compatibility with `__init__.py` re-exports or explicit migration edits plus tests.
6. **Smallest coherent diff**: split by responsibility, not by line-count shuffling.
7. **No detector camouflage**: never split strings/numbers (`"pri" + "mary"`), stitch constants (`PK_PRI + "mary"`), tuple-pack values, or add aliases just to dodge duplicate-literal/constant rules.

## Preemptive triggers — refactor *before* the hook denies

The cheapest refactor is the one done before any hook fires. Any of these conditions means split the module **now**, even if the current edit alone would not breach a threshold:

- **Line count is at ~250 and your edit adds code.** Do not wait for ~600 / `PY-CODE-018`. The split is cheaper before the function under edit grows further.
- **Function approaching budget.** A function at ~40 lines, ~9 cyclomatic complexity, or 4 params with a 5th obviously coming next iteration → extract the seam now, before `PY-CODE-008` / `PY-CODE-015` / `PY-CODE-009` denies the next write.
- **Class approaching method-count budget.** A class at 8 non-dunder methods and the current change adds the 9th or 10th → extract a collaborator before you hit 11 and `PY-CODE-014` denies the write. Group methods by the data they mutate or the collaborator they call; that grouping *is* the new class. Do not wait for the hook — by then you are refactoring under denial pressure with the new method already half-written.
- **Class crossed ~250 lines or has multiple distinct responsibilities visible.** Class-line and method-count budgets converge fast. If you can name two distinct domain concerns the class owns ("manages buffer state" + "writes archive to disk"), do the split now even if methods are at 7 — the next two edits will push it over and the second responsibility extracts cleanly today, painfully tomorrow.
- **God-class signal in tests.** If the class under edit needs 6+ fixtures, multiple `monkeypatch` setups per test, or test classes named after subsets of its methods (`TestUserAuth` + `TestUserProfile` + `TestUserBilling` for one `User` class), the production class is already a god-class waiting for `PY-CODE-014`. Extract collaborators now; the test split will follow naturally.
- **Shared-prefix sibling cluster forming.** Two files share a `<prefix>_` stem (`result_models.py`, `result_runner.py`) and the new code wants a `result_reconciliation.py`. **Stop.** Promote `result/` to a package before adding the third sibling. Three siblings is the antipattern, not the warning shot.
- **Touched-file lint not yet flagged but trending.** If `slopgate lint check` from repo root reports a new collector hit on the touched file (length / complexity / duplication / nesting), repair before unrelated edits, even if no PreToolUse hook denied the write.
- **Comment / docstring stripping urge.** If the only way a refactor "fits" is by removing module docstrings, removing inline `# Why this exists` comments, collapsing multi-line `try/except` into one-liners, or removing blank lines between logical groups, the refactor shape is wrong — split into a package and keep the explanatory text in the moved files.

When you make a preemptive split, the rules of the rule-specific recovery map below still apply: package directory over flat siblings, `__init__.py` re-exports for the public API, no facade-rebuild of the oversized module.

## First 90 seconds after a denial

1. Read the rule ID, path, and metadata/hits in the hook response.
2. Identify the current phase:
   - **PreToolUse / PermissionRequest**: proposed edit was blocked before landing; redesign the edit.
   - **PostToolUse / after-edit**: edit likely landed; inspect the touched file(s), repair, then verify.
3. Write a tiny repair plan in your own scratch context:
   - target files;
   - refactor shape;
   - public imports to preserve;
   - focused tests/compile command.
4. Search for existing helpers/constants/ownership before creating new abstractions. If the hook/lint response names an existing constant, import that exact symbol from the cited `path:line` instead of creating a duplicate.
5. Patch the design, not the guardrail.

## Rule-specific recovery map

### `PY-CODE-017` — flat sibling module cluster

Signal: files like `result_models.py`, `result_runner.py`, `result_reconciliation.py` are accumulating beside each other, or a new `prefix_*.py` appears beside an existing `prefix/` package. **Two `<prefix>_` siblings is the trigger to plan the package; the third sibling is too late** — if you find yourself about to write a third, do the package split instead. Do not rationalize "just one more flat file."

Preferred repair:

```text
# Before
src/agents/result_models.py
src/agents/result_runner.py
src/agents/result_reconciliation.py

# After
src/agents/result/
  __init__.py          # facade/re-exports stable API
  models.py
  runner.py
  reconciliation.py
```

Steps:

1. Create the package directory and an `__init__.py` facade.
2. Move cohesive pieces into package siblings; avoid another flat `prefix_*.py` file.
3. Preserve public imports with re-exports where safe:
   ```python
   from .models import ResultModel
   from .runner import ResultRunner

   __all__ = ["ResultModel", "ResultRunner"]
   ```
4. Update internal imports from `prefix_foo` to `prefix.foo` or package-relative imports.
5. Delete or move the old flat siblings in the same coherent patch when possible.
6. Verify compile/imports and focused tests before continuing.

Important nuance: mechanical filesystem moves may be the correct recovery step. Do not replace them with more flat files. After moves, make sure stale path mentions are not treated as still-existing modules.

### `PY-CODE-018` and oversized-module collectors

Signal: a proposed or existing Python module crosses the size threshold; `QUALITY-LINT-001` may surface the same condition after a write.

Preferred repair:

1. Identify natural seams: domain model, parser, renderer, adapter, CLI, tests, fixtures, constants, IO, validation, orchestration.
2. Convert `module.py` to `module/` package when callers import the module as an API surface.
3. Keep `__init__.py` thin: re-export public names only; do not rebuild the oversized module in the facade.
4. Move tests with the behavior or add focused tests around the seam being extracted.
5. For `conftest.py`: keep area-level `conftest.py` thin and import fixture implementations from `tests/<area>/_fixtures/` or `tests/<area>/support/` when the project allows that shape.
6. For generated/static literals: move to resources, fixtures, builders, or data files when appropriate.

Avoid these fake fixes:

- splitting by arbitrary line ranges;
- creating `utils.py` dumping grounds;
- moving code without updating import ownership;
- adding broad allowlists/baselines;
- making `__init__.py` as large as the old module.

### `PY-CODE-014` — god class

Signal: a class crossed >10 non-dunder methods, or `QUALITY-LINT-001` flagged class-body-size after a write.

Threshold reminder: the hook denies at >10 non-dunder methods. **The preemptive trigger is 8 methods with growth obvious in this PR**, not 11 with the hook in your face. Class-line budget (~250 lines) converges on the same bound; whichever budget you approach first is the trigger.

Recovery:

1. Identify the seam by **data + collaborators**, not by alphabetizing methods. A clean seam is a set of methods that share state with each other and barely touch the rest of the class. If the methods you would move all read/write the same three attributes that no other method touches, those attributes plus those methods are the new collaborator.
2. Name the collaborator after the responsibility (`RunArchiveStore`, `SnapshotPersister`), not after its parent (`EventBufferHelper`, `UserManager`). Inability to name the responsibility means the seam is wrong — re-plan.
3. Use constructor injection. The new collaborator gets its dependencies through `__init__` parameters. The parent class instantiates it once.
4. Move tests with the methods. If `TestUserAuth` covered the extracted methods, it follows them to a new test module — do not leave orphaned tests referencing methods that no longer exist on the parent.
5. After extraction, audit the parent. If it now consists of `__init__` plus four one-line delegating methods, that is `PY-CODE-013` waiting to fire. Either inline the parent's remaining behavior into the call site, or rename the collaborator to take the parent's place.

Anti-patterns to refuse:

- **Random method shuffling to get under 10.** Splitting by alphabetical order is hiding the smell, not fixing it.
- **`Helper` / `Manager` / `Service` suffix on the new class with no domain noun.** Re-plan the seam.
- **One-line wrapper methods on the parent that call into the new collaborator.** Move the callers, do not add wrappers.
- **Bidirectional dependency** (collaborator needs parent passed into `__init__`). The seam was wrong; the responsibility you extracted still depends on parent state.

See `references/refactoring_patterns.md` § "God class extraction" for the worked positive example (`cloud/services/event_buffer/`).

### `QUALITY-LINT-001` — post-edit lint backstop

Signal: a mutation landed and the touched file now has a quality violation.

Recovery:

1. Inspect the hook details for collector names and touched paths/hits.
2. Repair the landed change before any unrelated work.
3. If the finding is oversized-module/god-class/long-method/duplicate-helper, use the structural strategies in this skill.
4. If the finding is type-safety, load `type-strictness` too.
5. Run focused verification, then repo-root lint.

### Repeated literal / existing constant findings

Signal: `PY-QUALITY-010`, `PY-DUP-004`, `repeated-string-literal`, or a `QUALITY-LINT-001` detail says a literal is repeated, magic, or already defined as a constant.

Resolution strategy:

1. Use the cited existing constant location first. Good hook output should name the symbol and the owner, e.g. `PRIMARY_TIMEOUT_MS = 500 (src/constants.py:12)` or `import existing constant PRIMARY_TIMEOUT_MS from src/constants.py:12`.
2. Read that owner file before editing. Confirm the constant is semantically the same value/policy, not just coincidentally equal.
3. Import and reuse the existing symbol at call sites; preserve the owner module as the single source of truth.
4. If no existing constant is cited, create one near the owning domain (`constants.py`, `_constants.py`, config/defaults module, or a domain package constant), then replace all semantic duplicates intentionally.
5. Verify with the focused test/compile command and repo-root `slopgate lint check`.

Dirty fixes to reject:

- splitting a literal into fragments such as `"pri" + "mary"`;
- composing a duplicate from partial constants such as `PK_PRI + "mary"`;
- aliasing an existing constant under a new name without adding domain meaning;
- tuple/list packing or generated indirection whose only purpose is to change detector hashes;
- moving the value to `utils.py` or a random config file unrelated to the owning policy.

### `PY-AST-001` — parse/read failure

Recovery:

1. Re-read the file and restore parseability first.
2. Run `python3 -m py_compile <file>` or the project equivalent.
3. Only resume refactoring after syntax is clean.

### `PY-CODE-012`, `PY-CODE-013`, duplicate helpers, feature envy

Recovery:

- Thin wrapper: inline it or add meaningful validation, normalization, caching, error translation, or policy.
- Feature envy: move behavior to the object being inspected or introduce a domain method.
- Duplicate helper: search existing helpers/constants first; consolidate into the existing owner or a cohesive new module.
- Scattered utility: prefer a domain-owned module over `utils.py`.

## Blast-radius measurement (GitNexus-first, deterministic fallbacks)

Before any module-to-package split — preemptive or denial-driven — measure who imports the module and which symbols escape so the split preserves the public API.

**Preferred (when GitNexus is available and the index is fresh):**

```text
gitnexus_impact({target: "<symbol_or_module>", direction: "upstream"})
gitnexus_context({name: "<symbol>"})
gitnexus_detect_changes()   # before commit, after refactor
```

If any GitNexus tool reports the index is stale, run `npx gitnexus analyze` first; do not proceed on stale graph data.

**Fallback recipe when GitNexus is unavailable, stale, or not configured for this repo.** Each command is deterministic, fast, and avoids global filesystem scans. Replace `<MODULE>` with the dotted import path (e.g. `cloud.services.event_buffer._buffer`) and `<SYMBOL>` with the class/function name.

```bash
# 1. Direct importers — who would break if the module path changes
rg -n --pcre2 "^\s*(from\s+<MODULE>\s+import|import\s+<MODULE>)" -t py

# 2. Symbol callers / mentions — approximate when GitNexus is absent
rg -nw "<SYMBOL>" -t py

# 3. Public surface of the file under split — names callers can be reaching
rg -n "^(def|class|async def)\s+\w+" path/to/module.py
rg -n "^__all__\s*=" path/to/module.py

# 4. Module size + function-size signal
wc -l path/to/module.py
rg -n "^(def|class|async def) " path/to/module.py | wc -l

# 5. Cyclomatic / function-length spot check (radon if installed)
radon cc -s -a path/to/module.py
radon mi -s path/to/module.py

# 6. Co-change history — files that change together belong together
git log --pretty=format: --name-only --diff-filter=AM -- path/to/module.py \
  | grep -v '^$' | sort | uniq -c | sort -rn | head -20

# 7. Test files referencing the symbol (check coverage before moving)
rg -l "<SYMBOL>" tests/

# 8. Find similar-prefix siblings already accumulating in the same dir
ls path/to/dir/ | grep '^<prefix>_'
```

Treat the result of (1) and (7) as the authoritative caller list when no graph index is available. Anything imported only from inside the same package is safe to move freely; anything imported from elsewhere must keep its name reachable through the new `__init__.py` facade or get an explicit migration edit in the same PR.

If (6) consistently shows two files co-changing on every PR, that is the package boundary asking to exist — group them.

## Verification commands

Pick the smallest commands that prove the repair. Common Python/Slopgate sequence:

```bash
# Syntax for changed Python files
python3 -m py_compile path/to/changed.py

# Focused tests for touched behavior
python3 -m pytest tests/path/to/focused_test.py -q

# Slopgate quality gate from repo root; no path args
cd /path/to/repo && HOME=/home/trav /home/trav/.local/bin/slopgate lint check
```

When changing Slopgate itself:

```bash
cd /home/trav/.openclaw/workspace-hooker/slopgate
.venv/bin/python -m py_compile src/slopgate/engine.py src/slopgate/rules/python_ast/_rules.py
.venv/bin/python -m pytest tests/test_flat_file_sibling_packages.py tests/test_size_guard_hook_behavior.py -q
HOME=/home/trav .venv/bin/slopgate test
git diff --check
```

## When to escalate to `hygiene-orchestrator`

Load `hygiene-orchestrator` instead of doing a single local refactor when:

- multiple files or packages need coordinated hygiene repairs;
- many findings share an import graph or public API surface;
- parallel agents are useful but require file ownership boundaries;
- a repo-wide quality gate is failing after several local fixes.

## Reference docs

- `references/quality_rules.md` — current rule IDs and recovery strategies.
- `references/refactoring_patterns.md` — package split and smell-specific examples.
