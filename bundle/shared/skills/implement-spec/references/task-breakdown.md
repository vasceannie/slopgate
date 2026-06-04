# Task Breakdown Patterns

Strategies for decomposing implementation work into small, testable, verifiable units.

---

## Sizing Guidelines

### Atomic (Preferred)

Single responsibility, single test, single commit.

```
Task: Add ValidationError to domain errors
Verify: Import works, isinstance check passes
Files: 1 (domain/errors.py)
Time: 15 min
```

### Small

2-3 related items, same module.

```
Task: Create ProjectRole enum with permission methods
Verify: pytest tests/domain/test_project_role.py
Files: 1-2 (domain/identity/roles.py + test)
Time: 30 min
```

### Medium

Entity + repository + converter + tests.

```
Task: Implement Project entity with settings
Verify: pytest tests/domain/test_project.py
Files: 3-4 (entity, settings, tests, possibly errors)
Time: 1-2 hours
```

### Large → Split

If task feels large, split by:
- **Layer**: Domain → Infra → Application → API
- **CRUD operation**: Create → Read → Update → Delete
- **Feature aspect**: Core → Validation → Relationships

---

## Ordering Rules

### Layer Order (Dependency Flow)

```
1. Domain (no dependencies)
   └── Entities, value objects, enums
   └── Domain errors
   └── Port interfaces

2. Infrastructure (depends on domain)
   └── ORM models
   └── Repository implementations
   └── Converters

3. Application (depends on domain + infra)
   └── Services
   └── Use cases

4. API (depends on all)
   └── Proto/handlers
   └── Mixins

5. Client (depends on API)
   └── Commands
   └── UI components
```

### Feature Order (Incremental Capability)

```
1. Read-only first
   └── Get by ID
   └── List with filters

2. Write operations
   └── Create
   └── Update
   └── Delete/Archive

3. Relationships
   └── Associations
   └── Cascades

4. Advanced features
   └── Validation rules
   └── Business logic
```

---

## Decomposition Patterns

### Entity Pattern

```
1. Create entity dataclass with basic fields
2. Add validation methods
3. Add domain methods (archive, update, etc.)
4. Add related value objects
5. Add to domain exports
```

### Repository Pattern

```
1. Define port interface
2. Create ORM model
3. Write model converter
4. Implement repository methods
5. Register with UnitOfWork
```

### Service Pattern

```
1. Define service interface (if needed)
2. Inject dependencies
3. Implement core operation
4. Add validation layer
5. Add error handling
```

### API/RPC Pattern

```
1. Define proto messages
2. Define proto RPC
3. Regenerate stubs
4. Create mixin handler
5. Register with servicer
6. Add proto converter
```

---

## Task Templates

### Domain Entity

```yaml
task: Create [Entity] domain entity
verify: pytest tests/domain/test_[entity].py
steps:
  - Add dataclass to domain/entities/[entity].py
  - Add to domain/entities/__init__.py exports
  - Create test file with basic instantiation
depends: []
```

### Repository Port

```yaml
task: Define [Entity]Repository port interface
verify: Type check passes (basedpyright)
steps:
  - Add Protocol to domain/ports/repositories/[module].py
  - Define CRUD method signatures
  - Export from domain/ports/__init__.py
depends: [Entity domain entity]
```

### Repository Implementation

```yaml
task: Implement [Entity]Repository
verify: pytest tests/infrastructure/test_[entity]_repository.py
steps:
  - Create ORM model in persistence/models/
  - Create converter in infrastructure/converters/
  - Implement repository in persistence/repositories/
  - Add to UnitOfWork
depends: [Repository port, ORM model]
```

### gRPC Mixin

```yaml
task: Create [Entity]Mixin for gRPC handlers
verify: pytest tests/grpc/test_[entity]_handlers.py
steps:
  - Create mixin in grpc/_mixins/[entity].py
  - Add RPC handler methods
  - Create proto converters
  - Register with NoteFlowServicer
depends: [Proto messages, Service layer]
```

---

## Anti-Patterns

### Too Large

**Bad:**
```
Task: Implement entire Project feature
```

**Good:**
```
Task: Create Project entity
Task: Create ProjectSettings value object
Task: Create ProjectRole enum
Task: Implement ProjectRepository
...
```

### Missing Verification

**Bad:**
```
Task: Add user validation
```

**Good:**
```
Task: Add user validation
Verify: pytest tests/domain/test_user_validation.py -v
```

### Unclear Dependencies

**Bad:**
```
Task: Add project to meeting
```

**Good:**
```
Task: Add project_id FK to MeetingModel
Depends: ProjectModel ORM model exists
```

### Bundled Concerns

**Bad:**
```
Task: Add project with tests and migrations
```

**Good:**
```
Task: Create Project entity and tests
Task: Create ProjectModel ORM
Task: Create migration for projects table
```

---

## Progress Tracking

Use `TodoWrite` to track:

```python
todos = [
    {"content": "Create ProjectRole enum", "status": "completed"},
    {"content": "Create Project entity", "status": "in_progress"},
    {"content": "Create ProjectSettings VO", "status": "pending"},
    {"content": "Implement ProjectRepository", "status": "pending"},
]
```

**Status rules:**
- One `in_progress` at a time
- Mark `completed` immediately when done
- Add discovered tasks as `pending`
