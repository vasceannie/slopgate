# Specification Document Template

Use this template structure for implementation specifications. Adapt sections as needed—not all sections apply to every feature.

---

## Template

```markdown
# Sprint N: [Feature Name]

> **Size**: S/M/L/XL | **Owner**: [Team/Person] | **Prerequisites**: [Sprint X, Sprint Y]
> **Phase**: [N] - [Phase Name]

---

## Open Issues & Prerequisites

> [STATUS ICON] **Review Date**: YYYY-MM-DD — [Summary of review status]

### Blocking Issues

| ID | Issue | Status | Resolution |
|----|-------|--------|------------|
| **B1** | **[Issue description]** | [STATUS] | [Resolution or "Pending"] |
| **B2** | **[Issue description]** | [STATUS] | [Resolution or "Pending"] |

### Design Gaps to Address

| ID | Gap | Resolution |
|----|-----|------------|
| G1 | [Gap description] | [How to resolve] |
| G2 | [Gap description] | [How to resolve] |

### Prerequisite Verification

| Prerequisite | Status | Notes |
|--------------|--------|-------|
| [Prerequisite name] | [STATUS] | [Details] |

---

## Validation Status (YYYY-MM-DD)

### NOT IMPLEMENTED

| Component | Status | Notes |
|-----------|--------|-------|
| [Component name] | Not implemented | [Details] |

### PARTIALLY IMPLEMENTED

| Component | Status | Notes |
|-----------|--------|-------|
| [Component name] | Partial | [What exists vs missing] |

**Downstream impact**: [List dependent sprints/features]

---

## Objective

[2-3 sentences describing the goal. What capability does this enable? Why does it matter?]

---

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **[Decision area]** | [Choice made] | [Why this choice] |
| **[Decision area]** | [Choice made] | [Why this choice] |

---

## What Already Exists

| Asset | Location | Implication |
|-------|----------|-------------|
| [Existing code/pattern] | `path/to/file.py:lines` | [How to reuse] |
| [Existing code/pattern] | `path/to/file.py` | [How to reuse] |

---

## Scope

| Task | Effort | Notes |
|------|--------|-------|
| **Domain Layer** | | |
| [Task description] | S/M/L | [Details] |
| **Infrastructure Layer** | | |
| [Task description] | S/M/L | [Details] |
| **Application Layer** | | |
| [Task description] | S/M/L | [Details] |
| **API Layer** | | |
| [Task description] | S/M/L | [Details] |
| **Client Layer** | | |
| [Task description] | S/M/L | [Details] |

**Total Effort**: [Size] ([Time estimate])

---

## Domain Model

### [Entity Name] Entity

```python
# src/[project]/domain/entities/[entity].py

@dataclass
class [EntityName]:
    """[Description]."""

    id: UUID
    # ... fields with types and defaults
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def [method_name](self) -> [ReturnType]:
        """[Description]."""
        # Implementation notes
```

**Constraints**:
- [Constraint 1]
- [Constraint 2]

### [ValueObject/Enum Name]

```python
# src/[project]/domain/[module].py

class [EnumName](Enum):
    """[Description]."""

    VALUE_1 = "value_1"
    VALUE_2 = "value_2"

    def [helper_method](self) -> bool:
        return self in (...)
```

---

## API Schema

### Proto Additions (gRPC)

```protobuf
// [file].proto additions

enum [EnumName] {
  [ENUM]_UNSPECIFIED = 0;
  [ENUM]_VALUE_1 = 1;
  [ENUM]_VALUE_2 = 2;
}

message [MessageName] {
  string id = 1;
  // ... fields
}

message [Request]Request {
  string [field] = 1;
}

message [Request]Response {
  [MessageName] [field] = 1;
}

service [ServiceName] {
  rpc [MethodName]([Request]Request) returns ([Request]Response);
}
```

### REST Endpoints (if applicable)

| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | `/api/v1/[resource]` | `Create[Resource]Request` | `[Resource]` |
| GET | `/api/v1/[resource]/{id}` | — | `[Resource]` |

---

## Migration Strategy

### Phase 1: Schema
1. [Migration step]
2. [Migration step]

### Phase 2: Backfill
1. [Backfill step]
2. [Backfill step]

### Phase 3: Constraint (Sprint N+X)
1. [Constraint enforcement step]

### Migration Risks

| Risk | Mitigation |
|------|------------|
| [Risk description] | [Mitigation strategy] |

---

## Shared Types & Reuse Notes

- **[Type/utility to move]**: Move from `[current location]` to `[new location]`
- **[Pattern to reuse]**: Reuse `[existing pattern]` from `[location]`
- **[Integration point]**: Connect with `[existing feature]` via `[mechanism]`

---

## URL Routing (if applicable)

| Current Route | New Route | Notes |
|---------------|-----------|-------|
| `[old route]` | `[new route]` | [Changes] |
| — | `[new route]` | [New endpoint] |

---

## UI Components (if applicable)

### [ComponentName]

```tsx
// client/src/components/[path]/[Component].tsx

export function [ComponentName]({ [props] }: Props) {
  // Hook usage
  const { ... } = use[Hook]();

  return (
    <div>
      {/* Component structure */}
    </div>
  );
}
```

---

## Deliverables

### Backend

**Domain Layer**:
- [ ] `src/[project]/domain/entities/[entity].py` — [Description]
- [ ] `src/[project]/domain/[module].py` — [Description]

**Infrastructure Layer**:
- [ ] `src/[project]/infrastructure/persistence/models/[model].py` — [Description]
- [ ] `src/[project]/infrastructure/persistence/repositories/[repo].py` — [Description]
- [ ] `src/[project]/infrastructure/converters/[converter].py` — [Description]

**Application Layer**:
- [ ] `src/[project]/application/services/[service].py` — [Description]

**API Layer**:
- [ ] `src/[project]/[api]/proto/[file].proto` — [Description]
- [ ] `src/[project]/[api]/_mixins/[mixin].py` — [Description]

**Migrations**:
- [ ] `[migration_name]` — [Description]

### Client

- [ ] `client/src/[path]/[file].ts` — [Description]
- [ ] `client/src/components/[path]/[Component].tsx` — [Description]
- [ ] `client/src/hooks/use-[hook].ts` — [Description]

---

## Test Strategy

### Fixtures to extend or create

- `tests/conftest.py`: add [fixtures needed]
- `tests/[layer]/conftest.py`: add [layer-specific fixtures]

### Parameterized tests

- [Test category]: [Variations to parameterize]
- [Test category]: [Variations to parameterize]

### Core test cases

- **Domain**: [Key behaviors to test]
- **Service**: [Key behaviors to test]
- **API**: [Key behaviors to test]
- **Integration**: [End-to-end scenarios]

---

## Quality Gates

- [ ] `pytest tests/domain/test_[entity].py` passes
- [ ] `pytest tests/[layer]/test_[module].py` passes
- [ ] `npm run test` passes for frontend (if applicable)
- [ ] Meets quality standards (lint + test thresholds)
- [ ] No `# type: ignore` without justification
- [ ] All public functions have docstrings

---

## Post-Sprint

- [ ] [Future enhancement 1]
- [ ] [Future enhancement 2]
- [ ] [Future enhancement 3]
```

---

## Section Guidelines

### When to Include Each Section

| Section | Include When |
|---------|--------------|
| Open Issues | There are unresolved blockers or design gaps |
| Validation Status | Building on existing partial implementation |
| Key Decisions | Multiple valid approaches exist |
| What Already Exists | Reusable code found during analysis |
| Domain Model | New entities or value objects needed |
| API Schema | New endpoints or messages needed |
| Migration Strategy | Database schema changes required |
| URL Routing | Client routing changes needed |
| UI Components | New UI components needed |

### Effort Estimation

| Size | Time | Complexity |
|------|------|------------|
| **S** | 1-2 hours | Single file, clear pattern |
| **M** | 2-4 hours | 2-3 files, some decisions |
| **L** | 4-8 hours | Cross-cutting, integration needed |
| **XL** | 1-2 days | Architectural, multiple systems |

### Status Icons

- ✅ Complete/Resolved
- 🔨 In Progress/Adding
- ⚠️ Blocked/At Risk
- ❌ Not Started/Failed
