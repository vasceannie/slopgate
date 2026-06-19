from __future__ import annotations

from hypothesis import given, strategies

from slopgate.rules.langgraph import (
    LangGraphStateReducerRule,
    find_mutations,
    find_reducer_findings,
)


def test_langgraph_helpers_feed_lint_and_runtime_contracts() -> None:
    source = """
from typing import TypedDict
from langgraph.graph import StateGraph

class AgentState(TypedDict):
    messages: list[str]

def node(state):
    state["messages"].append("hello")
    return state
""".lstrip()

    reducer_findings = find_reducer_findings(
        "src/graph/workflow.py", source, LangGraphStateReducerRule()
    )
    mutations = find_mutations(source)

    assert {
        "reducer_classes": [item.metadata.get("class") for item in reducer_findings],
        "mutation_lines": [line_no for line_no, _preview in mutations],
    } == {
        "reducer_classes": ["AgentState"],
        "mutation_lines": [8],
    }, "LangGraph helper seams should expose reducer and mutation signals"


@given(
    lines=strategies.lists(
        strategies.sampled_from(("value = 1", "result = value + 1", "return result")),
        max_size=12,
    )
)
def test_find_reducer_findings_ignores_sources_without_state_signals(
    lines: list[str],
) -> None:
    source = "\n".join(lines)

    assert find_reducer_findings(
        "src/graph/empty.py", source, LangGraphStateReducerRule()
    ) == [], "find_reducer_findings should not invent reducers without StateGraph usage"


@given(
    lines=strategies.lists(
        strategies.sampled_from(("value = 1", "result = value + 1", "return result")),
        max_size=12,
    )
)
def test_find_mutations_ignores_sources_without_state_signals(
    lines: list[str],
) -> None:
    source = "\n".join(lines)

    assert find_mutations(source) == [], (
        "find_mutations should not report mutations when generated lines avoid state"
    )
