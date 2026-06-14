---
name: slopgate-hygiene-orchestrator
description: |
  Orchestrate systematic elimination of linter warnings and errors across Python, TypeScript, and Rust codebases. Use when asked to "clean up lints", "fix all warnings", "run hygiene", "eliminate type errors", "orchestrate code quality fixes", "fix lint errors", "resolve quality gate failures", "pass CI checks", "reduce tech debt", "refactor to pass hooks", or when a Slopgate hook denies with QUALITY-LINT-001, PY-CODE-017, PY-CODE-018, or any collector finding. This skill coordinates multiple code-hygiene-enforcer agents working in parallel on non-conflicting file groupings, tracks progress persistently via JSON exports, and loops until all issues are resolved. CRITICAL: Never run linters directly—always use `slopgate lint check` as the primary gate, discover project-specific tools from config files, and export findings to JSON for tracking.
version: 1.0.0
author: Slopgate
license: MIT
compatibility: claude-code, opencode, codex, hermes, slopgate
metadata:
  hermes:
    tags: [slopgate,lint,quality-gates,bulk-remediation,hygiene]
    related_skills: [slopgate-code-hygiene-refactor,slopgate-test-extender,slopgate-code-smell-utility-locator]
  slopgate:
    rule_ids: [QUALITY-LINT-001,PY-CODE-017,PY-CODE-018]
    activation:
      primary: [repo-wide lint cleanup,multi-file hook remediation,slopgate lint tracking]
      avoid: [single local denial,one-file refactor,test-only coverage gap]
---

# Hygiene Orchestrator

Coordinate systematic elimination of linter warnings/errors using parallelized agents, JSON-exported findings, and persistent progress tracking.

## When to Use

Use when the task is repo-wide, multi-file, or multi-rule Slopgate cleanup.

- User asks to fix all warnings, clean up lints, pass the quality gate, or coordinate hygiene work.
- `slopgate lint check --details` produces many findings that need grouping, tracking, and dispatch.
- Multiple files or collectors are involved and progress needs a persistent `.hygiene/` tracking artifact.
- Use this as the coordinator; delegate local structural repairs to `slopgate-code-hygiene-refactor` and test gaps to `slopgate-test-extender`.

## When Not to Use

Do not use for a single hook denial or one touched file. Use `slopgate-code-hygiene-refactor` for local structure, `slopgate-code-smell-utility-locator` for helper/constant ownership, and `slopgate-test-extender` for test-only findings.

Do not use when the task is only to inspect current telemetry or explain a rule without applying a cleanup plan.

## Critical Rules

1. **NEVER run linters directly in terminal** — Use `slopgate lint check` (repo root, no path args) as the primary gate. Discover project-specific tools by inspecting `package.json`, `pyproject.toml`, `Cargo.toml`, etc.
2. **Always export to JSON** — Lint outputs must be parsed into structured JSON for tracking and dispatch
3. **Update tracking before context compaction** — Progress must survive context limits via `.hygiene/tracking.json`
4. **Remind all agents about related skills** — Invoke `/type-strictness` for type fixes, `/code-hygiene-refactor` for structural issues, `/test-extender` for coverage gaps

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

### Primary: `slopgate lint check`

Run from the repo root. No path argument is accepted.

```bash
# Basic run
HOME=/home/trav /home/trav/.local/bin/slopgate lint check

# Detailed output with repair guidance
HOME=/home/trav /home/trav/.local/bin/slopgate lint check --details

# Export to JSON for parsing (pipe stdout to a parser)
HOME=/home/trav /home/trav/.local/bin/slopgate lint check --details 2>&1 | \
  python3 /path/to/skill/scripts/parse_slopgate_lint.py --output .hygiene/slopgate_lint.json
```

The `--details` flag adds per-finding fields: `file`, `location`, `signature`, `detail`, `stable-id`, `prognosis`, `scaffold`, `metadata.*`, `agent-context`, `validation`, `verify`.

### Secondary: project-specific lint tools

If the project uses additional linters beyond Slopgate, discover the correct invocation rather than assuming a Makefile:

```bash
# Look for common entrypoints
ls package.json 2>/dev/null && npm run lint --silent 2>/dev/null
ls pyproject.toml 2>/dev/null && python3 -m ruff check . 2>/dev/null
ls Cargo.toml 2>/dev/null && cargo clippy --all-targets 2>/dev/null
```

Pipe any secondary lint output through a parser into `.hygiene/` JSON or text. Do not assume `make` targets exist.

## Phase 2: Parse and Group Issues

### Parsing Slopgate Lint Output

Use `scripts/parse_slopgate_lint.py` to parse `--details` output into structured JSON:

```bash
python /path/to/skill/scripts/parse_slopgate_lint.py \
  --input <(slopgate lint check --details 2>&1) \
  --output .hygiene/slopgate_lint.json
```

The parser produces:

```json
{
  "header": {
    "project": "/path/to/repo",
    "baseline": "/path/to/repo/baselines.json"
  },
  "summary": {
    "collectors": [
      {"name": "long-method", "total": 3, "new": 2},
      {"name": "untested-production-code", "total": 1, "new": 1}
    ],
    "total_findings": 4,
    "new_findings": 3,
    "baseline_findings": 1,
    "fixed_findings": 0
  },
  "findings": [
    {
      "status": "NEW",
      "collector": "long-method",
      "fields": {
        "file": "src/main.py",
        "location": "src/main.py:52",
        "signature": "callable `f`",
        "detail": "lines=52",
        "stable-id": "long-method|src/main.py|f|lines=52",
        "prognosis": "function is doing multiple phases inline.",
        "scaffold": "extract named helpers for parse/validate/transform/persist/render phases; keep data flow explicit."
      }
    }
  ]
}
```

### Grouping Strategy

Group issues into **non-conflicting batches** for parallel agent work:

| Priority | Grouping Criteria | Rationale |
|----------|-------------------|-----------|
| 1 | By file (no overlaps) | Agents can't conflict on different files |
| 2 | By collector / error category | Similar fixes, consistent patterns |
| 3 | By severity | Errors before warnings |
| 4 | By dependency order | Fix imports/types before consumers |

**Non-conflicting batch rules:**
- Files in batch A share NO imports with files in batch B
- Type definition files before files that use those types
- Base classes before derived classes

Use `stable-id` to deduplicate findings across iterations.

## Phase 3: Dispatch Parallel Agents

### Agent Configuration

Each agent batch receives:
1. **File list**: Non-overlapping with other batches
2. **Issue manifest**: Specific findings with `stable-id`, `scaffold`, and `location`
3. **Context reminder**: Relevant skills, project conventions

### Dispatch Template

```yaml
# For each batch, spawn code-hygiene-enforcer agent:
batch_1:
  files: [src/noteflow/grpc/_mixins/annotation.py, src/noteflow/grpc/_mixins/calendar.py]
  findings:
    - stable-id: "long-method|src/noteflow/grpc/_mixins/annotation.py|parse|lines=65"
      scaffold: "extract named helpers for parse/validate/transform phases"
  agent: code-hygiene-enforcer
  instructions: |
    Fix the following issues. Remember: use /type-strictness skill for all type fixes.
    Never add # type: ignore. Update all dependent code.

batch_2:
  files: [src/noteflow/grpc/_mixins/project/_membership.py, src/noteflow/grpc/_mixins/project/_mixin.py]
  findings:
    - stable-id: "untested-production-code|src/noteflow/grpc/_mixins/project/_membership.py|coverage-001"
      scaffold: "add behavior tests for the unreferenced public symbols"
  agent: code-hygiene-enforcer
  instructions: |
    Fix None-safety issues. Add proper guards or update function signatures.
    Use /test-extender for test additions. Use /type-strictness for type refinements.
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

1. **Re-run slopgate lint**:
   ```bash
   HOME=/home/trav /home/trav/.local/bin/slopgate lint check --details 2>&1 | \
     python3 /path/to/skill/scripts/parse_slopgate_lint.py --output .hygiene/slopgate_lint.json
   ```

2. **Verify no regressions** with the project's test command:
   ```bash
   # Discover the test runner; don't assume make
   ls pytest.ini pyproject.toml tox.ini 2>/dev/null && python3 -m pytest -q
   ls package.json 2>/dev/null && npm test --silent 2>/dev/null
   ls Cargo.toml 2>/dev/null && cargo test --quiet 2>/dev/null
   ```

3. **Check for new issues** introduced by fixes

### Update Tracking File

Maintain `.hygiene/tracking.json`:

```json
{
  "session_id": "2025-01-02T03:45:00Z",
  "iteration": 3,
  "repo": "/path/to/repo",
  "baseline": "/path/to/repo/baselines.json",
  "initial_counts": {
    "long-method": 5,
    "untested-production-code": 3,
    "repeated-code-block": 12
  },
  "current_counts": {
    "long-method": 1,
    "untested-production-code": 0,
    "repeated-code-block": 4
  },
  "completed_items": [
    {
      "stable_id": "long-method|src/foo.py|process|lines=68",
      "file": "src/foo.py",
      "collector": "long-method",
      "resolved_at": "2025-01-02T04:00:00Z"
    }
  ],
  "pending_items": [
    {
      "stable_id": "long-method|src/bar.py|transform|lines=72",
      "file": "src/bar.py",
      "collector": "long-method",
      "scaffold": "extract named helpers for transform/persist phases",
      "status": "open"
    }
  ],
  "blocked_items": [
    {
      "stable_id": "repeated-code-block|src/qux.py|helper|lines 10-15",
      "file": "src/qux.py",
      "collector": "repeated-code-block",
      "reason": "Requires architectural change — shared helper needs design review"
    }
  ],
  "last_updated": "2025-01-02T04:15:00Z"
}
```

Use `stable-id` as the primary key for tracking individual findings across iterations.

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
    findings:
      - stable-id: "collector|file|signature|detail"
        scaffold: "repair guidance from slopgate output"
  instructions: |
    Continue hygiene orchestration from iteration 4.
    Read .hygiene/tracking.json for full state.
    Run /hygiene-orchestrator to resume.
```

## Iteration Loop

```
WHILE issues_remaining > 0:
    1. Export fresh lint results (slopgate lint check --details)
    2. Parse into JSON (parse_slopgate_lint.py)
    3. Group into non-conflicting batches by stable-id
    4. Dispatch agents in parallel
    5. Wait for completion
    6. Validate fixes (re-run slopgate lint check)
    7. Update tracking.json
    8. IF context_nearing_limit:
           Write handoff state
           EXIT with resume instructions
    9. Increment iteration
```

## Available Commands

| Command | Output | Description |
|---------|--------|-------------|
| `slopgate lint check` | stdout (human) | Repo-root lint, no path args |
| `slopgate lint check --details` | stdout (human + repair guidance) | Detailed with prognosis/scaffold |
| `parse_slopgate_lint.py` | `.hygiene/slopgate_lint.json` | Structured JSON from --details output |

Project-specific tools (discover, don't assume):

| Tool | Typical invocation |
|------|-------------------|
| ruff | `python3 -m ruff check .` |
| pyrefly | `pyrefly check --output-format json pyproject.toml` |
| biome | `npx biome check .` |
| tsc | `npx tsc --noEmit` |
| clippy | `cargo clippy --all-targets` |
| eslint | `npx eslint .` |

## Skill Reminders

Always remind dispatched agents:

1. **Use /type-strictness skill** for type annotations
2. **Use /test-extender skill** when modifying tested code or adding coverage
3. **Use /code-hygiene-refactor skill** for structural issues (flat siblings, oversized modules, god classes)
4. **Never use # type: ignore** — fix the underlying issue
5. **Never use Any** unless absolutely unavoidable
6. **Update all callers** when changing signatures
7. **Run tests** after fixes: `pytest <affected_tests>`

## Error Categories Reference

### Slopgate collectors (common)
- `long-method` — Function exceeds line threshold; extract helpers
- `repeated-code-block` — Duplicated behavior; extract shared helper/service
- `untested-production-code` — Public symbols lack test references; add behavior tests
- `flat-sibling-modules` — Files share prefix; convert to sub-package (see /code-hygiene-refactor)
- `oversized-module` — Module exceeds line threshold; split by responsibility
- `god-class` — Class has too many methods; extract collaborators

### Python (pyrefly)
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

1. Read `.hygiene/tracking.json`
2. Read `.hygiene/slopgate_lint.json`
3. Continue from `tracking.json.iteration`
4. Process `tracking.json.pending_items` by `stable-id`
