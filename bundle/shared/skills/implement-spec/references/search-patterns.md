# Search-Before-Edit Patterns

Mandatory codebase search strategies to find reusable code before any implementation.

---

## Search Philosophy

```
1. NEVER assume code needs to be written
2. ALWAYS search for existing patterns first
3. PREFER extending over creating
4. REUSE signatures and imports exactly
```

---

## Search Strategy Tiers

### Tier 1: Semantic Search (Serena Tools)

Best for finding symbols by name or pattern.

```python
# Find all services
find_symbol(name_path_pattern="*Service", depth=1, include_body=False)

# Find specific class
find_symbol(name_path_pattern="MeetingRepository", include_body=True)

# Find methods in a class
find_symbol(name_path_pattern="MeetingService/*", depth=1)

# Find with substring matching
find_symbol(name_path_pattern="*Repo", substring_matching=True)
```

### Tier 2: Pattern Search (Regex)

Best for finding code patterns across files.

```python
# Find dataclass definitions
search_for_pattern(
    substring_pattern="@dataclass",
    paths_include_glob="**/domain/**/*.py"
)

# Find enum definitions
search_for_pattern(
    substring_pattern="class.*Enum",
    paths_include_glob="**/domain/**"
)

# Find method signatures
search_for_pattern(
    substring_pattern="def create_.*self.*->",
    paths_include_glob="**/*service*.py"
)

# Find imports
search_for_pattern(
    substring_pattern="from noteflow.domain.entities import",
    paths_include_glob="**/*.py"
)
```

### Tier 3: Reference Search

Best for understanding usage patterns.

```python
# Find where UnitOfWork is used
find_referencing_symbols(
    name_path="UnitOfWork",
    relative_path="domain/ports/unit_of_work.py"
)

# Find callers of a method
find_referencing_symbols(
    name_path="MeetingService/create",
    relative_path="application/services/meeting_service.py"
)
```

### Tier 4: Overview Search

Best for understanding file structure.

```python
# Get file structure
get_symbols_overview(relative_path="domain/entities/meeting.py", depth=1)

# List directory
list_dir(relative_path="domain/ports/repositories", recursive=False)
```

---

## Common Search Scenarios

### Adding a New Entity

```python
# 1. Find existing entity patterns
find_symbol(name_path_pattern="Meeting", include_body=True)
get_symbols_overview(relative_path="domain/entities/meeting.py", depth=1)

# 2. Find where entities are exported
search_for_pattern(
    substring_pattern="__all__",
    paths_include_glob="**/domain/entities/__init__.py"
)

# 3. Find related value objects
search_for_pattern(
    substring_pattern="@dataclass.*frozen",
    paths_include_glob="**/domain/**"
)
```

### Adding a Repository

```python
# 1. Find repository interface patterns
find_symbol(name_path_pattern="*Repository", relative_path="domain/ports/")

# 2. Find implementation patterns
get_symbols_overview(relative_path="infrastructure/persistence/repositories/", depth=0)

# 3. Find converter patterns
search_for_pattern(
    substring_pattern="class.*Converter",
    paths_include_glob="**/infrastructure/converters/**"
)

# 4. Find UnitOfWork registration
find_symbol(name_path_pattern="SQLAlchemyUnitOfWork", include_body=True)
```

### Adding a Service

```python
# 1. Find existing services
find_symbol(name_path_pattern="*Service", relative_path="application/services/")

# 2. Find dependency injection patterns
search_for_pattern(
    substring_pattern="def __init__.*uow:",
    paths_include_glob="**/application/services/**"
)

# 3. Find error handling patterns
search_for_pattern(
    substring_pattern="raise.*Error",
    paths_include_glob="**/application/services/**"
)
```

### Adding gRPC Handler

```python
# 1. Find existing mixins
get_symbols_overview(relative_path="grpc/_mixins/", depth=0)

# 2. Find handler patterns
search_for_pattern(
    substring_pattern="async def.*request.*context",
    paths_include_glob="**/grpc/_mixins/**"
)

# 3. Find proto converter patterns
find_symbol(name_path_pattern="*_to_proto", relative_path="grpc/_mixins/")

# 4. Find how mixins are composed
find_symbol(name_path_pattern="NoteFlowServicer", include_body=True)
```

### Finding Test Fixtures

```python
# 1. Find conftest files
list_dir(relative_path="tests/", recursive=True)

# 2. Find fixtures by name pattern
search_for_pattern(
    substring_pattern="@pytest.fixture",
    paths_include_glob="**/conftest.py"
)

# 3. Find specific fixture
search_for_pattern(
    substring_pattern="def mock_uow",
    paths_include_glob="**/tests/**"
)
```

---

## Search Result Interpretation

### Found Match → Reuse

```
✅ Exact pattern found
   → Copy import statement
   → Follow same structure
   → Reuse base classes

Example: Found MeetingRepository
   → Use same base class pattern
   → Follow same method signatures
   → Reuse converter pattern
```

### Partial Match → Adapt

```
⚠️ Similar but not exact
   → Identify differences
   → Document adaptation needed
   → Maintain consistency

Example: Found UserService but need ProjectService
   → Same DI pattern
   → Same error handling
   → Different entities
```

### No Match → Ask Permission

```
❌ Nothing found
   → Document what was searched
   → Explain why new code needed
   → Ask user for permission

Example: No trigger provider found
   → "Searched: *Provider, *Trigger*, signal*"
   → "New file needed: triggers/calendar_provider.py"
   → "Proceed with creation?"
```

---

## Import Discovery

### Find Correct Import Path

```python
# Method 1: Find where symbol is exported
search_for_pattern(
    substring_pattern="from.*import.*Meeting",
    paths_include_glob="**/*.py",
    head_limit=10
)

# Method 2: Check package __init__.py
search_for_pattern(
    substring_pattern="Meeting",
    paths_include_glob="**/domain/**/__init__.py"
)

# Method 3: Find the actual definition
find_symbol(name_path_pattern="Meeting")
# Returns: domain/entities/meeting.py:42
# Import: from noteflow.domain.entities.meeting import Meeting
```

### Verify Import Works

```python
# Check if import exists in similar files
search_for_pattern(
    substring_pattern="from noteflow.domain.entities import",
    paths_include_glob="**/application/services/**"
)
```

---

## Quick Reference

| Goal | Tool | Pattern |
|------|------|---------|
| Find class | `find_symbol` | `name_path_pattern="ClassName"` |
| Find methods | `find_symbol` | `name_path_pattern="Class/*"` |
| Find pattern | `search_for_pattern` | `substring_pattern="@decorator"` |
| Find usage | `find_referencing_symbols` | `name_path="symbol"` |
| Find structure | `get_symbols_overview` | `relative_path="file.py"` |
| List files | `list_dir` | `relative_path="dir/"` |

---

## Anti-Patterns

### Writing Without Searching

**Bad:**
```python
# Just start coding
class ProjectRepository:
    ...
```

**Good:**
```python
# First search
find_symbol(name_path_pattern="*Repository", include_body=True)
# Then implement following found pattern
```

### Guessing Imports

**Bad:**
```python
from noteflow.entities import Project  # Guessed path
```

**Good:**
```python
# Search for actual export
search_for_pattern("from.*import.*Meeting", "**/services/**")
# Found: from noteflow.domain.entities import Meeting
# Use: from noteflow.domain.entities import Project
```

### Ignoring Found Patterns

**Bad:**
```python
# Found MeetingRepository uses AsyncRepository base
# But I'll use my own pattern
class ProjectRepository:
    ...
```

**Good:**
```python
# Follow found pattern exactly
class ProjectRepository(AsyncRepository[Project]):
    ...
```
