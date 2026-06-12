from __future__ import annotations

from pathlib import Path

from slopgate import rules
from slopgate.context import HookContext

from tests.integration.test_guard_rule_public_api import (
    context_for_payload,
    write_payload,
)


def langgraph_context(tmp_path: Path, source: str) -> HookContext:
    (tmp_path / "graph.py").write_text(source, encoding="utf-8")
    return context_for_payload(
        tmp_path, write_payload("graph.py", source, event="PostToolUse")
    )


def test_langgraph_state_reducer_rule_reports_bare_list_field(tmp_path: Path) -> None:
    source = """
from typing import TypedDict
from langgraph.graph import StateGraph

class State(TypedDict):
    messages: list[str]
""".lstrip()
    ctx = langgraph_context(tmp_path, source)

    findings = rules.LangGraphStateReducerRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("path")) for item in findings] == [
        ("LG-STATE-001", "graph.py")
    ]


def test_langgraph_state_mutation_rule_reports_direct_state_change(
    tmp_path: Path,
) -> None:
    mutation_line = 'state["messages"]' + '.append("hello")'
    source = f"""
from langgraph.graph import StateGraph

def node(state):
    {mutation_line}
    return state
""".lstrip()
    ctx = langgraph_context(tmp_path, source)

    findings = rules.LangGraphStateMutationRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("path")) for item in findings] == [
        ("LG-NODE-001", "graph.py")
    ]


def test_langgraph_deprecated_api_rule_reports_old_entrypoint_api(
    tmp_path: Path,
) -> None:
    old_entrypoint = "set_" + "entry_point"
    source = f"""
from langgraph.graph import StateGraph

graph = StateGraph(dict)
graph.{old_entrypoint}("node")
""".lstrip()
    ctx = langgraph_context(tmp_path, source)

    findings = rules.LangGraphDeprecatedAPIRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("path")) for item in findings] == [
        ("LG-API-001", "graph.py"),
    ]
