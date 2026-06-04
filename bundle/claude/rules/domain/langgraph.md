---
globs: **/graph/**/*.py, **/langgraph/**/*.py, **/graph.py
---

# LangGraph

## State reducers

Every `list` field in state needs `Annotated[list[T], operator.add]` — without it parallel writes silently overwrite.

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
```

## No direct mutation

Return new values; don't mutate state. Direct mutation bypasses reducers.

```python
# Good
def my_node(state) -> dict:
    return {"messages": [new_msg]}
```

## Nodes & edges

- Nodes are pure: `(state) -> partial_state_update`.
- `add_conditional_edges` with named routing functions, not lambdas.
- Descriptive node names (`"retrieve_documents"`, not `"step_2"`).

## Deprecated → modern

- `AgentExecutor` / `initialize_agent` → `create_react_agent` or graph builder.
- `ConversationChain` → message history in graph state.
- Verify patterns from tutorials >6 months old against current changelog.
