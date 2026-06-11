# Grouping Strategies for Parallel Agent Dispatch

Strategies for dividing lint issues into non-conflicting batches for parallel agent work.

## Core Principle: No File Overlap

**Golden Rule**: Two agents must NEVER work on the same file simultaneously.

Files are atomic units—even if issues are on different lines, concurrent edits cause conflicts.

## Strategy 1: File-Based Isolation

Simplest and safest approach.

### Algorithm

```python
def group_by_file(issues: list[Issue]) -> list[Batch]:
    by_file = defaultdict(list)
    for issue in issues:
        by_file[issue.file].append(issue)

    return [
        Batch(files=[f], issues=file_issues)
        for f, file_issues in by_file.items()
    ]
```

### Pros
- Zero conflict risk
- Simple to implement
- Maximum parallelism for unrelated files

### Cons
- May dispatch many small agents
- No optimization for related files

## Strategy 2: Directory-Based Grouping

Group files by directory to reduce agent count while maintaining isolation.

### Algorithm

```python
def group_by_directory(issues: list[Issue], max_files_per_batch: int = 5) -> list[Batch]:
    by_dir = defaultdict(list)
    for issue in issues:
        dir_path = Path(issue.file).parent
        by_dir[dir_path].append(issue)

    batches = []
    for dir_path, dir_issues in by_dir.items():
        files = list(set(i.file for i in dir_issues))
        # Split large directories
        for i in range(0, len(files), max_files_per_batch):
            batch_files = files[i:i + max_files_per_batch]
            batch_issues = [i for i in dir_issues if i.file in batch_files]
            batches.append(Batch(files=batch_files, issues=batch_issues))

    return batches
```

### Use When
- Many files in same directory have similar issues
- Directory represents logical unit (e.g., `_mixins/`)

## Strategy 3: Category-Based Grouping

Group by issue type to enable specialized fixes.

### Categories

| Category | Issue Codes | Fix Pattern |
|----------|-------------|-------------|
| `type-safety` | unbound-name, bad-argument-type | Add guards, narrow types |
| `none-safety` | missing-attribute, optional-access | Add None checks |
| `imports` | untyped-import, missing-import | Add stubs, fix paths |
| `dead-code` | unused, dead_code | Remove or use |
| `error-handling` | unwrap_used, expect_used | Add proper error handling |

### Algorithm

```python
def group_by_category(issues: list[Issue]) -> list[Batch]:
    by_category = defaultdict(list)
    for issue in issues:
        by_category[issue.category].append(issue)

    batches = []
    for category, cat_issues in by_category.items():
        # Further split by file to avoid conflicts
        by_file = defaultdict(list)
        for issue in cat_issues:
            by_file[issue.file].append(issue)

        # Group non-overlapping files
        current_batch_files = []
        current_batch_issues = []

        for file, file_issues in by_file.items():
            current_batch_files.append(file)
            current_batch_issues.extend(file_issues)

            if len(current_batch_files) >= 3:  # Batch size limit
                batches.append(Batch(
                    files=current_batch_files,
                    issues=current_batch_issues,
                    category=category
                ))
                current_batch_files = []
                current_batch_issues = []

        if current_batch_files:
            batches.append(Batch(
                files=current_batch_files,
                issues=current_batch_issues,
                category=category
            ))

    return batches
```

## Strategy 4: Dependency-Ordered Grouping

Process files in dependency order to avoid cascading issues.

### Dependency Order

1. **Type definitions** (`types.py`, `protocols.py`, `entities.py`)
2. **Base classes** (`_base.py`, abstract classes)
3. **Utilities** (`utils.py`, `helpers.py`)
4. **Domain logic** (services, repositories)
5. **Entry points** (CLI, API handlers)
6. **Tests** (`tests/`)

### Algorithm

```python
PRIORITY_ORDER = [
    r"types\.py$",
    r"protocols\.py$",
    r"entities\.py$",
    r"_base\.py$",
    r"utils\.py$",
    r"helpers\.py$",
    r"services/",
    r"repositories/",
    r"grpc/",
    r"cli/",
    r"tests/",
]

def get_priority(file: str) -> int:
    for i, pattern in enumerate(PRIORITY_ORDER):
        if re.search(pattern, file):
            return i
    return len(PRIORITY_ORDER)

def group_by_dependency_order(issues: list[Issue]) -> list[Batch]:
    by_file = defaultdict(list)
    for issue in issues:
        by_file[issue.file].append(issue)

    # Sort files by priority
    sorted_files = sorted(by_file.keys(), key=get_priority)

    # Create sequential batches (not parallel!)
    batches = []
    current_priority = -1
    current_batch = Batch(files=[], issues=[])

    for file in sorted_files:
        priority = get_priority(file)

        if priority != current_priority and current_batch.files:
            batches.append(current_batch)
            current_batch = Batch(files=[], issues=[])
            current_priority = priority

        current_batch.files.append(file)
        current_batch.issues.extend(by_file[file])

    if current_batch.files:
        batches.append(current_batch)

    return batches
```

### Use When
- Fixing type definitions that affect many consumers
- Base class changes that cascade to derived classes

## Strategy 5: Import Graph Partitioning

Advanced: Use import graph to find truly independent file clusters.

### Algorithm Sketch

```python
def build_import_graph(files: list[str]) -> dict[str, set[str]]:
    """Build directed graph of imports."""
    graph = {}
    for file in files:
        imports = extract_imports(file)  # Parse AST
        graph[file] = {resolve_import(i) for i in imports if resolve_import(i) in files}
    return graph

def find_connected_components(graph: dict[str, set[str]]) -> list[set[str]]:
    """Find sets of files that don't import each other."""
    # Convert to undirected graph
    undirected = defaultdict(set)
    for file, imports in graph.items():
        for imp in imports:
            undirected[file].add(imp)
            undirected[imp].add(file)

    visited = set()
    components = []

    for file in graph:
        if file in visited:
            continue

        component = set()
        queue = [file]
        while queue:
            f = queue.pop()
            if f in visited:
                continue
            visited.add(f)
            component.add(f)
            queue.extend(undirected[f] - visited)

        components.append(component)

    return components

def group_by_import_independence(issues: list[Issue]) -> list[Batch]:
    files = list(set(i.file for i in issues))
    graph = build_import_graph(files)
    components = find_connected_components(graph)

    by_file = defaultdict(list)
    for issue in issues:
        by_file[issue.file].append(issue)

    return [
        Batch(
            files=list(component),
            issues=[i for f in component for i in by_file[f]]
        )
        for component in components
    ]
```

### Use When
- Large codebase with distinct modules
- Want maximum parallelism with safety guarantee

## Recommended Approach

Combine strategies for best results:

```python
def optimal_grouping(issues: list[Issue]) -> list[list[Batch]]:
    """Return batches in waves (each wave can run in parallel)."""

    # Wave 1: Fix type definitions and base classes (sequential)
    type_files = [i for i in issues if is_type_definition(i.file)]
    wave1 = group_by_file(type_files)  # Sequential

    # Wave 2: Fix by category (parallel within wave)
    remaining = [i for i in issues if not is_type_definition(i.file)]
    wave2 = group_by_category(remaining)

    return [wave1, wave2]
```

## Batch Size Guidelines

| Scenario | Max Files per Batch | Rationale |
|----------|---------------------|-----------|
| Type errors | 3-5 | Often cascade, need verification |
| Dead code | 10+ | Independent removals |
| Import fixes | 5-8 | May affect related files |
| Test fixes | 5-10 | Usually isolated |

## Conflict Detection

Before dispatching, verify no conflicts:

```python
def has_conflicts(batches: list[Batch]) -> bool:
    all_files = []
    for batch in batches:
        all_files.extend(batch.files)
    return len(all_files) != len(set(all_files))
```

## Agent Dispatch Pattern

```python
async def dispatch_wave(batches: list[Batch]) -> list[AgentResult]:
    """Dispatch all batches in parallel, wait for all to complete."""
    tasks = [
        Task(
            subagent_type="code-hygiene-enforcer",
            prompt=build_agent_prompt(batch),
            run_in_background=True
        )
        for batch in batches
    ]

    # Launch all
    task_ids = [await launch(t) for t in tasks]

    # Wait for all
    results = [await TaskOutput(task_id=tid, block=True) for tid in task_ids]

    return results
```
