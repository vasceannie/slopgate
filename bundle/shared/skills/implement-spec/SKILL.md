---
name: implement-spec
description: |
  Orchestrate disciplined implementation from requirements documents or user prompts. Use when:
  (1) User provides a sprint README, requirements doc, or implementation plan to execute
  (2) User asks to "implement", "build", or "develop" a feature with detailed requirements
  (3) User wants to break down a large effort into testable, verifiable tasks
  (4) User asks to execute work described in @docs/sprints/ or similar planning documents
  Enforces: task breakdown, search-before-edit, quality compliance, test coverage, type safety, and documentation reconciliation.
---

# Implementation Orchestrator

Execute implementation work through disciplined task breakdown, mandatory code search, and quality enforcement.

## Core Principles

| Principle | Enforcement |
|-----------|-------------|
| **Small, testable tasks** | Break all work into single-responsibility units |
| **Search before edit** | Every code edit preceded by codebase search |
| **No new files without permission** | Ask user before creating new modules |
| **Quality compliance** | All changes must pass `make quality` |
| **Type safety** | Use type-strictness skill for typing issues |
| **Test coverage** | Use test-extender skill for all tests |
| **Issue tracking** | Never ignore issues; document or create tasks |
| **Doc reconciliation** | Update related sprint/roadmap docs on completion |

## Workflow

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐    ┌──────────────────┐
│  1. PARSE       │───▶│  2. CLARIFY      │───▶│  3. BREAKDOWN   │───▶│  4. IMPLEMENT    │
│  Requirements   │    │  (if unclear)    │    │  Into Tasks     │    │  Each Task       │
└─────────────────┘    └──────────────────┘    └─────────────────┘    └──────────────────┘
                              │                       │                       │
                              ▼                       ▼                       ▼
                       requirements-spec        TodoWrite               Search → Edit
                       skill                    small units             → Test → Quality
                                                                              │
                                                                              ▼
                                                                    ┌──────────────────┐
                                                                    │  5. RECONCILE    │
                                                                    │  Documentation   │
                                                                    └──────────────────┘
```

## Phase 1: Parse Requirements

Accept input from:
- **Sprint README**: `@docs/sprints/phase-X/sprint-N/README.md`
- **Requirements doc**: Any structured implementation plan
- **User prompt**: Direct description of work to be done

Extract from document:
- Objective and scope
- Deliverables list (checkbox items)
- Domain model definitions
- API/Proto schema additions
- Migration requirements
- Test strategy
- Quality gates

## Phase 2: Clarify Requirements

If requirements are unclear, incomplete, or ambiguous, invoke the **requirements-spec** skill:

```
Use requirements-spec skill to:
1. Ask clarifying questions (2-4 per round)
2. Analyze codebase for existing patterns
3. Produce enriched specification
```

**Clarity checklist:**
- [ ] Scope boundaries defined (backend/fullstack/client)
- [ ] Entities and relationships clear
- [ ] API contracts specified
- [ ] Migration strategy defined
- [ ] Test cases identified
- [ ] Quality gates explicit

## Phase 3: Break Down Into Tasks

Convert requirements into small, testable, verifiable tasks using `TodoWrite`.

### Task Sizing Rules

| Size | Characteristics |
|------|-----------------|
| **Atomic** | Single function, single test, single file (preferred) |
| **Small** | 2-3 related functions, same module |
| **Medium** | Single entity + repository + tests |
| **Large** | Split into smaller tasks |

### Task Ordering

1. **Domain layer first** — Entities, value objects, errors
2. **Infrastructure adapters** — Repositories, converters
3. **Application services** — Business logic orchestration
4. **API layer** — Proto, mixins, handlers
5. **Tests in parallel** — Write tests alongside implementation
6. **Client last** — Frontend changes after backend stable

### Task Template

```
Task: [ACTION] [COMPONENT] for [PURPOSE]
Verify: [HOW TO TEST]
Depends: [PREREQUISITE TASKS]
```

Example:
```
Task: Create ProjectRole enum with permission methods
Verify: pytest tests/domain/test_project_role.py
Depends: None

Task: Add ProjectModel with FK to WorkspaceModel
Verify: alembic upgrade head (no errors)
Depends: ProjectRole enum

Task: Implement ProjectRepository with CRUD operations
Verify: pytest tests/infrastructure/test_project_repository.py
Depends: ProjectModel
```

## Phase 4: Implement Each Task

### 4.1 Search Before Edit (MANDATORY)

Before ANY code edit, search the codebase to find:

```python
# Find similar implementations
find_symbol(name_path_pattern="*Service", depth=1, include_body=False)
find_symbol(name_path_pattern="*Repository", depth=1)

# Find specific patterns
search_for_pattern(substring_pattern="@dataclass", paths_include_glob="**/domain/**")

# Find usage patterns for reuse
find_referencing_symbols(name_path="UnitOfWork", relative_path="domain/ports/")

# Keyword search for signatures
search_for_pattern(substring_pattern="def create_", paths_include_glob="**/*service*.py")
```

**Search requirements:**
- [ ] Find existing similar implementations
- [ ] Identify base classes/protocols to extend
- [ ] Locate imports and their signatures
- [ ] Check for conflicting names
- [ ] Find related test fixtures

### 4.2 Ask Permission for New Files

If search yields no satisfactory match:

```
Before creating [new_file.py]:
- Purpose: [why needed]
- Location: [proposed path]
- Alternatives considered: [what was searched]

Proceed with file creation? (Ask user)
```

### 4.3 Implement with Quality

Write code following patterns found in search:

```python
# Match existing conventions
# - Import style from same package
# - Error handling patterns
# - Docstring format
# - Type annotation style
```

### 4.4 Write Tests (test-extender skill)

For every implementation, use **test-extender** skill:

```
Invoke test-extender to:
1. Find existing test fixtures to reuse
2. Check for parametrization opportunities
3. Follow quality rules (no loops, no conditionals in tests)
4. Use proper assertion messages
```

### 4.5 Fix Type Issues (type-strictness skill)

For any typing errors or `Any` usage, invoke **type-strictness** skill:

```
Invoke type-strictness to:
1. Infer types from codebase
2. Find type stubs if needed
3. Inspect library signatures
4. Apply type guards/narrowing
5. Document casts (last resort)
```

### 4.6 Run Quality Checks

```bash
make quality
```

**Quality gates:**
- All tests pass
- No type errors
- No lint violations
- No test anti-patterns

## Phase 5: Reconcile Documentation

After implementation complete:

### 5.1 Update Sprint/Task Documents

```bash
# Find related docs
rg -l "Sprint 18" docs/
rg -l "[Feature Name]" docs/sprints/
```

Update:
- [ ] Mark deliverables as complete
- [ ] Update validation status
- [ ] Resolve blocking issues
- [ ] Add discovered issues to "Open Issues"

### 5.2 Update Roadmap

If implementation changes affect future sprints:
- Update prerequisite status
- Note downstream impacts
- Add discovered work to backlog

### 5.3 Document Issues

**Never ignore issues.** For each issue encountered:

| Action | When |
|--------|------|
| **Fix immediately** | Small, in-scope issue |
| **Create task** | Medium issue, related to current work |
| **Add to doc** | Larger issue, out of scope |
| **Open issue** | Cross-cutting, needs discussion |

## Issue Handling

### Preexisting Issues

When encountering preexisting issues:

1. **Acknowledge** — Note the issue in your response
2. **Assess impact** — Does it block current task?
3. **Document** — Add to sprint doc or create task
4. **Decide action**:
   - Fix if small and in-scope
   - Create explicit task if medium
   - Escalate to user if large

### Implementation Issues

When hitting problems during implementation:

```
Issue: [Description]
Impact: [How it affects current work]
Options:
  1. [Option with trade-offs]
  2. [Option with trade-offs]
Recommendation: [Your suggestion]
```

Ask user before proceeding with workarounds.

## Tool Integration

| Tool/Skill | Phase | Purpose |
|------------|-------|---------|
| `TodoWrite` | 3 | Track task breakdown and progress |
| `find_symbol` | 4.1 | Semantic code search |
| `search_for_pattern` | 4.1 | Keyword/regex search |
| `find_referencing_symbols` | 4.1 | Find usage patterns |
| `AskUserQuestion` | 4.2 | Permission for new files |
| **test-extender** | 4.4 | Test creation and quality |
| **type-strictness** | 4.5 | Type safety enforcement |
| **requirements-spec** | 2 | Clarification if needed |

## Guardrails

Call these before major actions:

| Tool | When |
|------|------|
| `think_about_collected_information` | After search, before edit |
| `think_about_task_adherence` | Before implementing each task |
| `think_about_whether_you_are_done` | After completing all tasks |

## Quick Reference

### Before Every Edit

1. Search codebase (semantic + keyword)
2. Find imports and signatures
3. Check for existing patterns
4. Confirm no new files without permission

### After Every Task

1. Run tests for that component
2. Check types (`pyrefly check`)
3. Run quality checks
4. Mark task complete in TodoWrite

### On Completion

1. Run full quality suite (`make quality`)
2. Update sprint documentation
3. Document any new issues
4. Reconcile with roadmap

## References

- `references/task-breakdown.md` — Task sizing and ordering patterns
- `references/search-patterns.md` — Code search strategies and examples
