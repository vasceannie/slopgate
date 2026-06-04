
# LangGraph Patterns

Enforcer hooks have dedicated LangGraph rules for state reducers, mutation, and deprecated APIs.

## State Reducers

- Every `list` field in state **must** have an `Annotated[list[T], operator.add]` reducer
- Without a reducer, parallel node outputs silently overwrite each other
- Use `operator.add` for append semantics, custom reducers for merge/dedup

```python
# Good — reducer declared
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    documents: Annotated[list[Document], operator.add]

# Bad — no reducer, parallel writes overwrite
class AgentState(TypedDict):
    messages: list[BaseMessage]  # last writer wins silently
```

## State Mutation

- **Never mutate state directly** — return new values from nodes
- LangGraph merges returned dicts through reducers; direct mutation bypasses them

```python
# Bad — direct mutation
def my_node(state: AgentState) -> AgentState:
    state["messages"].append(new_msg)  # bypasses reducer
    return state

# Good — return new values for reducer to merge
def my_node(state: AgentState) -> dict:
    return {"messages": [new_msg]}
```

## Graph Construction

- Define nodes as pure functions: `(state) -> partial_state_update`
- Use `add_conditional_edges` with explicit routing functions, not lambda
- Name nodes descriptively: `"retrieve_documents"` not `"step_2"`

## Deprecated APIs

- `AgentExecutor` → use `create_react_agent` or graph builder
- `initialize_agent` → use graph builder with explicit nodes
- `ConversationChain` → use message history with graph state
- Check LangGraph changelog before using patterns from tutorials >6 months old
