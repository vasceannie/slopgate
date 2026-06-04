# Clarification Question Bank

Organized questions for gathering requirements. Use `AskUserQuestion` with 2-4 questions per round.

---

## By Domain

### Scope & Boundaries

| Trigger | Question | Options |
|---------|----------|---------|
| Feature boundaries unclear | "Which components are in scope?" | Backend only, Full-stack, Client only |
| MVP vs full unclear | "What's the minimum viable version?" | [Specific options based on feature] |
| Layer coverage unknown | "Should this include persistence, or is it in-memory only?" | Persisted, In-memory, Configurable |
| Timeline unclear | "Is this for the current sprint or future planning?" | Current sprint, Next sprint, Roadmap item |

### Actors & Access Control

| Trigger | Question | Options |
|---------|----------|---------|
| No roles mentioned | "Who can perform this action?" | All users, Admins only, Role-based |
| Ownership unclear | "Is this scoped to user, workspace, or global?" | User-scoped, Workspace-scoped, Global |
| Permission inheritance unclear | "Should workspace admins have implicit access?" | Yes (implicit), No (explicit only), Configurable |
| Multi-tenancy unclear | "Can data be shared across workspaces?" | Isolated, Shared, Configurable |

### Data Model & Relationships

| Trigger | Question | Options |
|---------|----------|---------|
| Entities without relationships | "How does [A] relate to [B]?" | One-to-one, One-to-many, Many-to-many |
| Lifecycle unclear | "Can these be archived or deleted?" | Soft delete, Hard delete, Archive only |
| Cascade behavior unknown | "What happens to related data on delete?" | Cascade, Restrict, Orphan |
| Uniqueness unclear | "Should [field] be unique?" | Globally unique, Scoped unique, Not unique |
| Required fields unknown | "Which fields are required vs optional?" | [List fields for clarification] |

### Integration & Dependencies

| Trigger | Question | Options |
|---------|----------|---------|
| Standalone vs connected unclear | "Does this integrate with existing features?" | Standalone, Integrates with [X], Replaces [X] |
| API contract unknown | "Should this expose a public API?" | Internal only, Public API, Both |
| Event-driven unclear | "Should this emit events for other systems?" | No events, Webhooks, Internal events |
| External dependencies | "Does this require external services?" | No dependencies, Optional, Required |

### Constraints & NFRs

| Trigger | Question | Options |
|---------|----------|---------|
| Performance unclear | "Are there performance requirements?" | Real-time (<100ms), Interactive (<1s), Background |
| Scale unclear | "What's the expected data volume?" | Small (<1K), Medium (<100K), Large (>100K) |
| Security requirements | "Are there security constraints?" | Standard auth, Encryption required, Audit logging |
| Availability requirements | "What's the uptime requirement?" | Best effort, 99%, 99.9%+ |

### UI & UX

| Trigger | Question | Options |
|---------|----------|---------|
| UI needed unclear | "Does this need a UI component?" | No UI, Simple form, Complex interface |
| Navigation unclear | "Where should this appear in the UI?" | Sidebar, Header, Settings, New page |
| Interaction pattern unknown | "What's the primary interaction?" | View only, CRUD, Real-time updates |
| Mobile support unclear | "Should this work on mobile?" | Desktop only, Responsive, Mobile-first |

---

## By Feature Type

### New Entity/Resource

1. **Data Model**: "What are the core fields for [Entity]?"
2. **Relationships**: "How does [Entity] relate to existing entities?"
3. **Lifecycle**: "What states can [Entity] be in?"
4. **Access**: "Who can create/read/update/delete [Entity]?"

### Settings/Configuration

1. **Scope**: "Is this user-level, workspace-level, or global?"
2. **Inheritance**: "Should child scopes inherit from parent?"
3. **Defaults**: "What are sensible default values?"
4. **Validation**: "What constraints apply to these settings?"

### Integration/Webhook

1. **Trigger**: "What events should trigger this integration?"
2. **Payload**: "What data should be included?"
3. **Reliability**: "What retry/failure behavior is needed?"
4. **Security**: "How should requests be authenticated?"

### Background Job

1. **Trigger**: "What initiates this job?"
2. **Duration**: "How long should it run before timeout?"
3. **Failure**: "What happens if the job fails?"
4. **Visibility**: "Should users see job progress?"

### Migration/Refactor

1. **Backward Compatibility**: "Must the old behavior continue working?"
2. **Data Migration**: "How should existing data be transformed?"
3. **Rollback**: "What's the rollback strategy?"
4. **Cutover**: "Big bang or gradual rollout?"

---

## Question Patterns

### Option-Based Questions

Use when choices are discrete and known:

```yaml
questions:
  - header: "Scope"
    question: "Should this feature include client-side implementation?"
    multiSelect: false
    options:
      - label: "Backend only (Recommended)"
        description: "API and domain layer only, client work deferred"
      - label: "Full-stack"
        description: "Backend + React components + Tauri commands"
      - label: "Client only"
        description: "Frontend changes only, backend already exists"
```

### Multi-Select Questions

Use when multiple options can apply:

```yaml
questions:
  - header: "Events"
    question: "Which events should trigger webhooks?"
    multiSelect: true
    options:
      - label: "Created"
        description: "When a new resource is created"
      - label: "Updated"
        description: "When a resource is modified"
      - label: "Deleted"
        description: "When a resource is removed"
      - label: "State change"
        description: "When status/state transitions"
```

### Clarification Chains

Start broad, narrow based on answers:

```
Round 1: "Is this a new feature or enhancement to existing?"
  → New feature: "What existing features should it integrate with?"
  → Enhancement: "Which aspect needs improvement?"

Round 2: Based on answer, ask about specific constraints
Round 3: Confirm understanding with summary question
```

---

## Anti-Patterns

### Avoid These

| Anti-Pattern | Why | Instead |
|--------------|-----|---------|
| Too many questions at once | Overwhelms user | Max 4 questions per round |
| Yes/No questions | Limited information | Offer specific options |
| Vague questions | Ambiguous answers | Be specific about what you need |
| Technical jargon | Confuses non-technical users | Use plain language |
| Assumptions baked in | Biases answers | Neutral framing |

### Good vs Bad Examples

**Bad**: "Should we use PostgreSQL?"
**Good**: "What database requirements exist?" with options for relational, document, in-memory

**Bad**: "Is performance important?"
**Good**: "What's the acceptable response time?" with options for real-time, interactive, background

**Bad**: "Do you want tests?"
**Good**: "What test coverage is needed?" with options for unit, integration, e2e, all
