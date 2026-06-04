---
name: requirements-spec
description: |
  Gather requirements and produce comprehensive implementation specifications through interactive clarification and codebase analysis. Use when:
  (1) User requests a new feature implementation plan
  (2) User wants to enrich or validate an existing sprint/implementation document
  (3) User asks "what do I need to build X" or "help me plan Y"
  (4) User provides vague requirements needing clarification
  (5) User wants to identify reusable code before implementing
  Produces structured specification documents with blocking issues, domain models, API schemas, migration strategies, deliverables, and test plans.
---

# Requirements & Specifications

Produce implementation-ready specification documents through iterative clarification and codebase validation.

## Workflow

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  1. CLARIFY     │───▶│  2. ANALYZE      │───▶│  3. SYNTHESIZE  │
│  Requirements   │    │  Codebase        │    │  Specification  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
     │                       │                       │
     ▼                       ▼                       ▼
  AskUserQuestion      Semantic + Grep         Markdown Document
  (2-4 questions)      (find reusable code)   (Sprint README format)
```

## Phase 1: Clarify Requirements

Use `AskUserQuestion` with 2-4 focused questions per round. Stop when sufficient clarity exists.

### Question Categories

| Category | When Missing | Example |
|----------|--------------|---------|
| **Scope** | Feature boundaries unclear | "Backend only, full-stack, or client-only?" |
| **Actors** | No roles/permissions mentioned | "Who can perform this? Role restrictions?" |
| **Data** | Entities without relationships | "How does [A] relate to [B]?" |
| **Integration** | Standalone vs connected unclear | "Does this integrate with existing features?" |
| **Constraints** | NFRs not specified | "Performance, security, or compatibility requirements?" |
| **Priority** | MVP vs full feature unclear | "What's minimum viable vs nice-to-have?" |

### Clarification Patterns

**Ambiguous scope**: Ask about boundaries and priority breakdown.

**Missing actors**: Ask about access control and ownership scope (user/workspace/global).

**Unclear data model**: Ask about relationships and lifecycle (archive/delete behavior).

**Integration uncertainty**: Ask about existing feature touchpoints and API contracts.

## Phase 2: Analyze Codebase

Find reusable patterns, existing implementations, and integration points using parallel searches.

### Search Strategy

```python
# Semantic search (similar patterns)
find_symbol(name_path_pattern="*Service", depth=1)
find_symbol(name_path_pattern="*Repository", depth=1)

# Keyword search (specific implementations)
search_for_pattern(substring_pattern="@dataclass", paths_include_glob="**/domain/**")

# Reference search (usage patterns)
find_referencing_symbols(name_path="UnitOfWork", relative_path="domain/ports/")
```

### What to Find

| Category | Search Target | Purpose |
|----------|---------------|---------|
| **Domain** | Entities, value objects | Reuse field patterns, validation |
| **Services** | Application services | Follow established DI, error handling |
| **Repositories** | Port definitions | Match existing CRUD patterns |
| **API** | Proto messages, RPCs | Consistent API design |
| **Tests** | Fixtures, parameterized tests | Reuse test infrastructure |
| **Migrations** | Alembic scripts | Follow migration conventions |

### Validation Checklist

- [ ] No duplicate implementations exist
- [ ] Identified base classes/protocols to extend
- [ ] Found related features for integration
- [ ] Located test fixtures to reuse
- [ ] Checked for conflicting naming

## Phase 3: Synthesize Specification

Generate specification following `references/output-template.md`. Key sections:

1. **Header** — Sprint name, size, owner, prerequisites, phase
2. **Open Issues** — Blocking issues, design gaps, prerequisite verification
3. **Validation Status** — What exists vs needs implementation
4. **Objective** — 2-3 sentence goal
5. **Key Decisions** — Table with rationale
6. **What Already Exists** — Reusable assets from analysis
7. **Scope** — Task breakdown with effort (S/M/L/XL)
8. **Domain Model** — Entity definitions with code
9. **API Schema** — Proto/gRPC or REST additions
10. **Migration Strategy** — Phased rollout with risks
11. **Deliverables** — Checkbox lists by layer
12. **Test Strategy** — Fixtures, parameterized tests, cases
13. **Quality Gates** — Exit criteria

### Effort Guide

| Size | Scope |
|------|-------|
| **S** | Single file, straightforward (add field, simple function) |
| **M** | Multiple files, clear pattern (new entity, repo method) |
| **L** | Cross-cutting, some complexity (new service, gRPC mixin) |
| **XL** | Architectural, high complexity (new subsystem, major refactor) |

## Tool Usage

| Tool | Phase | Purpose |
|------|-------|---------|
| `AskUserQuestion` | 1 | Gather requirements |
| `find_symbol` | 2 | Semantic code search |
| `search_for_pattern` | 2 | Regex code search |
| `find_referencing_symbols` | 2 | Find usage patterns |
| `get_symbols_overview` | 2 | Understand file structure |
| `Write` | 3 | Generate specification |

### Guardrails

- `think_about_collected_information` — After Phase 2
- `think_about_task_adherence` — Before writing spec
- `think_about_whether_you_are_done` — After document complete

## References

- `references/output-template.md` — Full specification document template
- `references/question-bank.md` — Comprehensive clarification questions
