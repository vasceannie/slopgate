---
name: hygiene-orchestrator
description: |
  Orchestrate systematic elimination of all linter warnings and errors across Python, TypeScript, and Rust codebases. Use when asked to "clean up lints", "fix all warnings", "run hygiene", "eliminate type errors", or "orchestrate code quality fixes". This skill coordinates multiple code-hygiene-enforcer agents working in parallel on non-conflicting file groupings, tracks progress persistently, and loops until all issues are resolved. CRITICAL: Never run linters directly—always use Makefile targets that export to .hygeine/.
---

# Hygiene Orchestrator

Coordinate systematic elimination of linter warnings/errors using parallelized agents and persistent progress tracking.

## Critical Rules

1. **NEVER run linters directly in terminal** — Use Makefile targets exclusively
2. **Always export to .hygeine/** — Lint outputs must be persisted for parsing
3. **Update tracking before context compaction** — Progress must survive context limits
4. **Remind all agents about type-strictness skill** — Invoke `/type-strictness` for type fixes

## Workflow Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  1. Export      │───>│  2. Parse &      │───>│  3. Dispatch    │
│  Lint Results   │    │  Group Issues    │    │  Parallel Agents│
└─────────────────┘    └──────────────────┘    └─────────────────┘
         ^                                              │
         │              ┌──────────────────┐            │
         └──────────────│  4. Validate &   │<───────────┘
                        │  Update Tracking │
                        └──────────────────┘
```

## Phase 1: Export Lint Results

Run Makefile targets to populate `.hygeine/`:

```bash
# Python lints (pyrefly + basedpyright)
make lint-py                    # → .hygeine/pyrefly.txt
make type-check-py 2>&1 | tee .hygeine/basedpyright.txt

# TypeScript lints
make lint                       # → .hygeine/biome.json
make type-check 2>&1 | tee .hygeine/tsc.txt

# Rust lints
make clippy                     # → .hygeine/clippy.json
make lint-rs                    # → .hygeine/rust_code_quality.txt
```

**Auto-fixable first**: Run `make lint-fix-py` and `make lint-fix` before manual fixes.

## Phase 2: Parse and Group Issues

### Parsing Lint Outputs

Use `scripts/parse_lints.py` to parse all outputs into unified format:

```bash
python /path/to/skill/scripts/parse_lints.py .hygeine/ --output .hygeine/unified_issues.json
```

### Grouping Strategy

Group issues into **non-conflicting batches** for parallel agent work:

| Priority | Grouping Criteria | Rationale |
|----------|-------------------|-----------|
| 1 | By file (no overlaps) | Agents can't conflict on different files |
| 2 | By error category | Similar fixes, consistent patterns |
| 3 | By severity | Errors before warnings |
| 4 | By dependency order | Fix imports/types before consumers |

**Non-conflicting batch rules:**
- Files in batch A share NO imports with files in batch B
- Type definition files before files that use those types
- Base classes before derived classes

See `references/grouping_strategies.md` for detailed algorithms.

## Phase 3: Dispatch Parallel Agents

### Agent Configuration

Each agent batch receives:
1. **File list**: Non-overlapping with other batches
2. **Issue manifest**: Specific errors/warnings to fix
3. **Context reminder**: Type-strictness skill, project conventions

### Dispatch Template

```yaml
# For each batch, spawn code-hygiene-enforcer agent:
batch_1:
  files: [src/noteflow/grpc/_mixins/annotation.py, src/noteflow/grpc/_mixins/calendar.py]
  issues: [unbound-name, missing-attribute]
  agent: code-hygiene-enforcer
  instructions: |
    Fix the following issues. Remember: use /type-strictness skill for all type fixes.
    Never add # type: ignore. Update all dependent code.

batch_2:
  files: [src/noteflow/grpc/_mixins/project/_membership.py, src/noteflow/grpc/_mixins/project/_mixin.py]
  issues: [bad-argument-type]
  agent: code-hygiene-enforcer
  instructions: |
    Fix None-safety issues. Add proper guards or update function signatures.
    Use /type-strictness for type refinements.
```

### Parallel Execution

Use Task tool to launch multiple agents simultaneously:

```
Task(subagent_type="code-hygiene-enforcer", prompt="...", run_in_background=true)
Task(subagent_type="code-hygiene-enforcer", prompt="...", run_in_background=true)
...
```

Monitor with `TaskOutput(task_id=..., block=true)`.

## Phase 4: Validate and Update Tracking

### Post-Agent Validation

After each agent completes:

1. **Re-run affected linters**:
   ```bash
   make lint-py PY_TARGETS="<fixed_files>"
   make type-check-py PY_TARGETS="<fixed_files>"
   ```

2. **Verify no regressions**:
   ```bash
   pytest tests/quality/ -q
   ```

3. **Check for new issues** introduced by fixes

### Update Tracking File

Maintain `.hygeine/tracking.json`:

```json
{
  "session_id": "2025-01-02T03:45:00Z",
  "iteration": 3,
  "initial_counts": {
    "python_errors": 45,
    "python_warnings": 120,
    "typescript_errors": 12,
    "rust_warnings": 8
  },
  "current_counts": {
    "python_errors": 12,
    "python_warnings": 45,
    "typescript_errors": 0,
    "rust_warnings": 2
  },
  "completed_files": ["src/foo.py", "src/bar.py"],
  "pending_files": ["src/baz.py"],
  "blocked_issues": [
    {"file": "src/qux.py", "reason": "Requires architectural change"}
  ],
  "last_updated": "2025-01-02T04:15:00Z"
}
```

## Context Compaction Protocol

**CRITICAL**: Before context limit is reached, MUST update:

1. **tracking.json** with current progress
2. **Todo list** with remaining work items
3. **Memory** (if using Serena): Write to `hygiene_progress` memory

### Handoff Message Template

```yaml
hygiene_handoff:
  status: "in_progress"
  iteration: 4
  remaining_errors: 12
  next_batch:
    files: [list of files]
    issues: [list of issue types]
  instructions: |
    Continue hygiene orchestration from iteration 4.
    Read .hygeine/tracking.json for full state.
    Run /hygiene-orchestrator to resume.
```

## Iteration Loop

```
WHILE issues_remaining > 0:
    1. Export fresh lint results (Makefile targets)
    2. Parse unified issues
    3. Group into non-conflicting batches
    4. Dispatch agents in parallel
    5. Wait for completion
    6. Validate fixes
    7. Update tracking.json
    8. IF context_nearing_limit:
           Write handoff state
           EXIT with resume instructions
    9. Increment iteration
```

## Available Makefile Targets

| Target | Output File | Description |
|--------|-------------|-------------|
| `make lint-py` | `.hygeine/pyrefly.txt` | Python lints (pyrefly) |
| `make type-check-py` | (stdout) | Python types (basedpyright) |
| `make lint-fix-py` | `.hygeine/ruff.fix.json` | Auto-fix Python |
| `make lint` | `.hygeine/biome.json` | TypeScript lints |
| `make type-check` | (stdout) | TypeScript types |
| `make lint-fix` | - | Auto-fix TypeScript |
| `make clippy` | `.hygeine/clippy.json` | Rust lints |
| `make lint-rs` | `.hygeine/rust_code_quality.txt` | Rust quality |

## Skill Reminders

Always remind dispatched agents:

1. **Use /type-strictness skill** for type annotations
2. **Use /test-extender skill** when modifying tested code
3. **Never use # type: ignore** — fix the underlying issue
4. **Never use Any** unless absolutely unavoidable
5. **Update all callers** when changing signatures
6. **Run tests** after fixes: `pytest <affected_tests>`

## Error Categories Reference

### Python (pyrefly/basedpyright)
- `unbound-name` — Variable may be uninitialized
- `missing-attribute` — Method called on None
- `bad-argument-type` — Type mismatch in function call
- `untyped-import` — Missing type stubs
- `not-iterable` — Async iteration issues

### TypeScript (biome/tsc)
- `noExplicitAny` — Replace Any with specific type
- `noUnusedVariables` — Remove or use the variable
- `useConst` — Prefer const over let

### Rust (clippy)
- `clippy::unwrap_used` — Handle errors properly
- `clippy::expect_used` — Provide context or use ?
- `dead_code` — Remove unused code

## Resumption Protocol

If starting fresh after compaction:

1. Read `.hygeine/tracking.json`
2. Read `.hygeine/unified_issues.json`
3. Continue from `tracking.json.iteration`
4. Process `tracking.json.pending_files`
