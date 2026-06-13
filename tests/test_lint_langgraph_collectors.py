from __future__ import annotations

import keyword
from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, strategies

from slopgate.lint._detectors.langgraph import (
    detect_langgraph_builder_api,
    detect_langgraph_state_mutations,
    detect_langgraph_state_reducers,
)
from slopgate.lint._helpers import ParsedFile, parse_files
from slopgate.lint._config import load_config, reset_config

IDENTIFIERS = strategies.from_regex(r"[a-z][a-z_]{0,12}", fullmatch=True).filter(
    lambda value: value not in keyword.kwlist
)


def parsed_file(tmp_path: Path, source: str, name: str) -> list[ParsedFile]:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return parse_files([path])


def parsed_temp_source(source: str, name: str) -> list[ParsedFile]:
    with TemporaryDirectory() as raw_path:
        return parsed_file(Path(raw_path), source, name)


def test_langgraph_detectors_report_batch_source_findings(tmp_path: Path) -> None:
    load_config(tmp_path)
    parsed = parsed_file(
        tmp_path,
        """
from typing import TypedDict
from langgraph.graph import StateGraph

class AgentState(TypedDict):
    messages: list[str]

def node(state):
    state["messages"].append("hello")
    return state

graph = StateGraph(AgentState)
graph.set_entry_point("node")
""".lstrip(),
        "src/graph/workflow.py",
    )

    findings = [
        *detect_langgraph_state_reducers(parsed),
        *detect_langgraph_state_mutations(parsed),
        *detect_langgraph_builder_api(parsed),
    ]
    reset_config()

    assert [(item.rule, item.identifier) for item in findings] == [
        ("langgraph-state-reducer", "AgentState"),
        ("langgraph-state-mutation", "line-8"),
        ("langgraph-deprecated-api", "set_entry_point()"),
    ], "Expected LangGraph CLI collectors to mirror LG-* source checks"


def test_langgraph_detectors_ignore_non_langgraph_sources(tmp_path: Path) -> None:
    load_config(tmp_path)
    parsed = parsed_file(
        tmp_path,
        """
def node(state):
    state["messages"].append("hello")
    return state
""".lstrip(),
        "src/plain.py",
    )

    findings = [
        *detect_langgraph_state_reducers(parsed),
        *detect_langgraph_state_mutations(parsed),
        *detect_langgraph_builder_api(parsed),
    ]
    reset_config()

    assert findings == [], "Non-LangGraph sources should not produce LG CLI findings"


@given(IDENTIFIERS)
def test_langgraph_state_reducer_ignores_plain_sources_property(name: str) -> None:
    with_no_langgraph = f"def {name}():\n    return []\n"
    parsed = parsed_temp_source(with_no_langgraph, "plain_langgraph_prop.py")
    assert detect_langgraph_state_reducers(parsed) == [], (
        "Plain Python sources should not produce LangGraph reducer findings"
    )


@given(IDENTIFIERS)
def test_langgraph_state_mutation_ignores_plain_sources_property(name: str) -> None:
    with_no_langgraph = f"def {name}(state):\n    state['value'] = 1\n    return state\n"
    parsed = parsed_temp_source(with_no_langgraph, "plain_langgraph_prop.py")
    assert detect_langgraph_state_mutations(parsed) == [], (
        "State mutation text outside LangGraph context should not produce findings"
    )


@given(IDENTIFIERS)
def test_langgraph_builder_api_ignores_plain_sources_property(name: str) -> None:
    with_no_langgraph = f"def {name}(graph):\n    graph.set_entry_point('node')\n"
    parsed = parsed_temp_source(with_no_langgraph, "plain_langgraph_prop.py")
    assert detect_langgraph_builder_api(parsed) == [], (
        "Legacy-looking API text outside LangGraph context should not produce findings"
    )
