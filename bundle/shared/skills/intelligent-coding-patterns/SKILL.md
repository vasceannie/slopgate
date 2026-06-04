---
name: intelligent-coding-patterns
description: |
  Pattern-selection playbook for agents editing code with complex branching, stateful parsers/workflows, duplicated skeletons, policy checks, or ordered transforms. Load before refactoring if/elif dispatch chains, boolean-flag state machines, repeated validation predicates, parallel provider/language implementations, or regex/content transformation pipelines. Use with behavior-locking tests and avoid pattern theater for simple one-off code.
---

# Intelligent Coding Patterns

Use this skill when a code edit touches branching, dispatch, parser state, validation policies, duplicated extraction/provider logic, or ordered content/data transforms. The goal is not to add fashionable abstractions. The goal is to pick the smallest proven structure that makes the code easier to change, easier to test, and harder to break silently.

## Non-negotiables

1. Lock behavior before refactoring. Add or identify focused tests for the current behavior before changing the shape.
2. Prefer the smallest useful pattern. Two simple branches do not need a framework.
3. Preserve public APIs unless the task explicitly includes a migration.
4. Do not weaken hooks, tests, baselines, type checks, lint config, or rule thresholds to make a pattern refactor pass.
5. Keep the happy path readable. A pattern that makes the main flow harder to understand is probably the wrong pattern.
6. Verify with the narrowest relevant test first, then the broader gate if the touched project requires it.

## Pattern scout: classify the code before editing

Before editing a complex function, answer these shape questions:

1. Is this selecting behavior by key, protocol, type, command, provider, model, file extension, language, or event name?
   - Prefer Dispatch Table / Registry.
2. Is this code nested because edge cases wrap the happy path?
   - Prefer Guard Clauses.
3. Are boolean flags modeling parser/workflow state across a loop?
   - Prefer explicit State Pattern with enums and transitions.
4. Are repeated booleans enforcing named policy, validation, or eligibility checks?
   - Prefer Specification Pattern.
5. Do two or more functions/classes share the same skeleton but vary by parser/provider/language/storage implementation?
   - Prefer Template Method plus Strategy.
6. Are several transforms applied in order to the same content/object?
   - Prefer Pipeline / Chain of Responsibility.
7. Is the apparent pattern only one branch, one call site, or speculative future growth?
   - Skip the pattern and keep direct code.

## Dispatch Table / Registry

Use when behavior is selected by a stable key and there are three or more branches, or when new keys are expected.

Replaces:

```python
if protocol == "rest":
    return handle_rest(request)
elif protocol == "grpc":
    return handle_grpc(request)
elif protocol == "graphql":
    return handle_graphql(request)
raise UnsupportedProtocolError(protocol)
```

Prefer:

```python
PROTOCOL_HANDLERS: dict[str, Callable[[Request], Response]] = {
    "rest": handle_rest,
    "grpc": handle_grpc,
    "graphql": handle_graphql,
}

handler = PROTOCOL_HANDLERS.get(protocol)
if handler is None:
    raise UnsupportedProtocolError(protocol)
return handler(request)
```

When to use:

- command routers;
- provider/model handlers;
- protocol handlers;
- extension-to-parser maps;
- event name to hook handler maps.

Avoid when:

- the branches are fewer than three and unlikely to grow;
- each branch has deeply different control flow and shared dispatch would hide important behavior;
- the selected behavior depends on complex ordered predicates rather than exact keys.

Verification:

- one test per registered key;
- one unsupported-key test;
- one test that proves registration does not change existing behavior.

## Guard Clauses

Use when validation, missing dependencies, empty input, or safety checks force the happy path into nested indentation.

Replaces:

```python
def get_models() -> list[dict[str, str]]:
    if api_key:
        try:
            return fetch_models(api_key)
        except ProviderError:
            return []
    else:
        return []
```

Prefer:

```python
def get_models() -> list[dict[str, str]]:
    if not api_key:
        return []

    try:
        return fetch_models(api_key)
    except ProviderError:
        return []
```

When to use:

- missing config / missing credentials returns;
- invalid inputs;
- no-op cases;
- permission/safety preconditions;
- unsupported platform checks.

Avoid when:

- many early returns make cleanup/resource handling unclear;
- a context manager or transaction boundary needs one obvious exit path;
- error reporting needs accumulated failures rather than immediate return.

Verification:

- test each guard condition;
- test the happy path stays top-level and unchanged.

## State Pattern

Use when a loop carries boolean flags such as `in_string`, `escape_next`, `seen_header`, `pending_tool`, `inside_block`, or `awaiting_response`.

Replaces boolean flag mazes:

```python
in_string = False
escape_next = False
for char in text:
    if escape_next:
        ...
    elif in_string and char == "\\":
        ...
    elif in_string and char == "'":
        ...
    elif not in_string and char == ",":
        ...
```

Prefer an explicit state enum:

```python
from enum import Enum, auto

class ParserState(Enum):
    NORMAL = auto()
    IN_STRING = auto()
    ESCAPING = auto()

state = ParserState.NORMAL
for char in text:
    match state:
        case ParserState.ESCAPING:
            current.append(char)
            state = ParserState.IN_STRING
        case ParserState.IN_STRING:
            if char == "\\":
                current.append(char)
                state = ParserState.ESCAPING
            elif char == "'":
                current.append(char)
                state = ParserState.NORMAL
            else:
                current.append(char)
        case ParserState.NORMAL:
            if char == "'":
                current.append(char)
                state = ParserState.IN_STRING
            elif char == ",":
                emit_value()
            else:
                current.append(char)
```

When to use:

- parsers;
- streaming protocol readers;
- tool-call/session lifecycle handling;
- retry/backoff lifecycle code;
- multiline text scanners.

Avoid when:

- the state is truly binary and local;
- a standard parser/library exists and should be used instead;
- a table-driven parser would be clearer than match/case.

Verification:

- table-driven tests for each transition;
- boundary cases for empty input, escaped delimiters, delimiters inside strings, malformed/incomplete state, and final flush behavior;
- regression tests from real bug examples if available.

## Specification Pattern

Use when named checks, policies, or eligibility predicates are scattered as booleans or repeated if-statements.

Replaces scattered predicates:

```python
if not searched_context:
    failures.append("search context")
if not tools_ready:
    failures.append("tools ready")
if unsafe_target:
    failures.append("safe target")
```

Prefer named specs:

```python
@dataclass(frozen=True)
class CheckSpec:
    id: str
    description: str
    check: Callable[[TaskContext], bool]
    repair_hint: str

PRETASK_CHECKS = [
    CheckSpec("context-search", "Context search completed", lambda ctx: ctx.searched_context, "Search existing implementations first."),
    CheckSpec("tools-ready", "Required tools are available", lambda ctx: ctx.tools_ready, "Verify tool availability before editing."),
    CheckSpec("safe-target", "Target path is safe to edit", lambda ctx: not ctx.unsafe_target, "Stop and ask before mutating protected config."),
]

def evaluate_specs(ctx: TaskContext) -> list[CheckSpec]:
    return [spec for spec in PRETASK_CHECKS if not spec.check(ctx)]
```

When to use:

- pre-task checklists;
- policy gates;
- validation rules;
- eligibility filters;
- reusable rule explanations.

Avoid when:

- checks need one-off local context and will not be reused;
- a simple validation function is clearer;
- check order has side effects that should be explicit.

Verification:

- one test per spec;
- one aggregate test for multiple failures;
- one test proving descriptions/hints are stable if user-facing.

## Template Method plus Strategy

Use when two functions share a skeleton but differ in provider, parser, storage, language, or platform behavior.

Shape:

```python
class FunctionExtractor(ABC):
    def extract(self, path: Path) -> list[FunctionInfo]:
        source = self._read_source(path)
        raw = self._parse_signatures(source, path)
        calls = self._count_calls(source)
        return self._enrich(raw, calls)

    @abstractmethod
    def _parse_signatures(self, source: str, path: Path) -> list[FunctionInfo]: ...

    @abstractmethod
    def _count_calls(self, source: str) -> dict[str, int]: ...

class PythonExtractor(FunctionExtractor): ...
class TypeScriptExtractor(FunctionExtractor): ...

EXTRACTORS: dict[str, FunctionExtractor] = {
    ".py": PythonExtractor(),
    ".ts": TypeScriptExtractor(),
    ".tsx": TypeScriptExtractor(),
}
```

When to use:

- Python vs TypeScript extraction;
- provider-specific request builders with shared validation/response handling;
- platform adapters with shared envelope behavior;
- storage backends with shared orchestration.

Avoid when:

- duplication is superficial and names differ but logic does not;
- composition with small functions is enough;
- inheritance would obscure data flow or make tests harder.

Verification:

- shared skeleton test using a fake strategy;
- concrete strategy tests for each variant;
- registry test for extension/provider/platform routing.

## Pipeline / Chain of Responsibility

Use when content or data is transformed by a sequence of independent steps.

Replaces long in-function transform chains:

```python
content = normalize_links(content)
content = convert_captions(content)
content = rewrite_youtube_embeds(content)
content = sanitize_html(content)
return content
```

Prefer explicit pipeline composition when the chain is growing:

```python
class Transform(Protocol):
    name: str
    def apply(self, content: str) -> str: ...

class ContentPipeline:
    def __init__(self, transforms: Sequence[Transform]) -> None:
        self._transforms = list(transforms)

    def process(self, content: str) -> str:
        for transform in self._transforms:
            content = transform.apply(content)
        return content
```

When to use:

- regex/content conversion;
- AST or lint collector passes;
- data cleaning stages;
- request/response middleware;
- hook enrichment/rendering steps.

Avoid when:

- the order is fixed and only two simple lines;
- transforms share hidden mutable state;
- failure handling needs transaction semantics rather than a linear chain.

Verification:

- unit test each transform;
- integration test the ordered pipeline;
- test that order-sensitive transforms stay in the documented order.

## Testing playbook for pattern refactors

1. Characterize the existing behavior with narrow tests before changing code.
2. Include edge cases that motivated the pattern, not only the happy path.
3. Refactor in the smallest slice that preserves public behavior.
4. Run focused tests after each slice.
5. Run the local project quality gate only after the focused tests pass.
6. If a hook/lint backstop denies the refactor, repair the design. Do not suppress the rule.

Good test shapes:

- Dispatch tables: registered key, unsupported key, handler exception path.
- Guard clauses: missing input/config, invalid input, happy path.
- State machines: each transition, final flush, malformed/incomplete input.
- Specs: individual pass/fail, aggregated failures, user-facing hint text.
- Strategy/template: fake strategy for skeleton, concrete strategy for variants.
- Pipelines: individual transforms, ordered integration, idempotency where expected.

## Anti-patterns this skill should prevent

- Pattern theater: adding abstract base classes for one local if statement.
- Registry without tests: moving branches into a dict but not proving each key works.
- State enum cosplay: enum exists but boolean flags still drive the real behavior.
- Over-shared template: forcing different flows into one inheritance tree until each override is a workaround.
- Pipeline opacity: transforms mutate hidden global state or silently depend on undocumented order.
- Refactor without behavior lock: “cleaner” code with no test proving equivalence.

## Agent prompt/rule integration snippet

Use this as thin routing text in Claude, OpenCode, Codex, or Cursor markdown; keep this full skill as the canonical playbook:

```text
When editing code with branching or duplicated control flow, check for these refactor opportunities before writing:
- 3+ if/elif branches selecting behavior by key/type/protocol/provider/event -> dispatch table/registry.
- nested happy path -> guard clauses.
- boolean flags modeling parser/workflow state -> enum state machine.
- repeated validation/policy booleans -> specification objects.
- duplicated skeleton with variant parsing/provider/platform behavior -> template method + strategy.
- ordered regex/content/data transforms -> pipeline/chain.

If two or more triggers appear, load skill intelligent-coding-patterns before editing. Do not introduce these patterns for single-use or obviously simpler code. Add or identify behavior-locking tests before refactoring.
```

## Slopgate hook guidance

For advisory hook responses, prefer solution-first language:

```text
[QUALITY-PATTERN-002 | ADVISORY | PRE-WRITE]
This looks like behavior dispatch by protocol with 5 branches. Prefer a registry mapping protocol -> handler. Load intelligent-coding-patterns, section Dispatch Table. If this is intentionally local/simple, keep the direct branch and document why.
```

Start advisory-first for these pattern smells. Promote to blocking only for high-confidence cases such as new boolean-flag parser loops without tests, new 5+ branch key dispatch chains, or repeated ignored advisories on the same file/rule.
