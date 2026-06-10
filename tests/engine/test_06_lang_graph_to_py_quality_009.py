from __future__ import annotations

from tests.test_engine import (
    ObjectDict,
    Path,
    WriteBuilder,
    evaluate_payload,
    finding_ids,
    object_dict,
    pytest,
)


class TestLangGraph:
    def posttool_payload(
        self, tmp_project: Path, rel_path: str, code: str
    ) -> ObjectDict:
        target = tmp_project / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(code)
        return object_dict(
            {
                "session_id": "t",
                "cwd": str(tmp_project),
                "hook_event_name": "PostToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": rel_path, "content": code},
                "tool_response": {"filePath": rel_path, "success": True},
            }
        )

    @pytest.mark.parametrize(
        "code, should_flag",
        [
            pytest.param(
                "from typing import TypedDict\nfrom langgraph.graph import StateGraph\n"
                "class MyState(TypedDict, total=False):\n    messages: list[str]\n    counter: int\n",
                True,
                id="bare-list-field-flagged",
            ),
            pytest.param(
                "from typing import Annotated, TypedDict\nfrom operator import add\n"
                "from langgraph.graph import StateGraph\n"
                "class MyState(TypedDict, total=False):\n    messages: Annotated[list[str], add]\n    counter: int\n",
                False,
                id="annotated-list-not-flagged",
            ),
        ],
    )
    def test_lg_state_001(
        self, tmp_project: Path, code: str, should_flag: bool
    ) -> None:
        payload = self.posttool_payload(tmp_project, "graph/state.py", code)
        result = evaluate_payload(payload)
        finding = next(
            (f for f in result.findings if f.rule_id == "LG-STATE-001"), None
        )
        assert (not should_flag and finding is None) or (
            should_flag
            and finding is not None
            and finding.decision is None
            and "messages" in (finding.additional_context or "")
        ), f"Unexpected LG-STATE-001 result for code:\n{code}"

    @pytest.mark.parametrize(
        "code, should_flag",
        [
            pytest.param(
                "from langgraph.graph import StateGraph\n"
                'def my_node(state):\n    state["counter"] = state["counter"] + 1\n    return state\n',
                True,
                id="subscript-assign-flagged",
            ),
            pytest.param(
                "from langgraph.graph import StateGraph\n"
                'def my_node(state):\n    state["items"].append("new")\n    return state\n',
                True,
                id="append-flagged",
            ),
            pytest.param(
                'def my_node(state):\n    val = state.get("counter", 0)\n    return {"counter": val + 1}\n',
                False,
                id="get-read-only-not-flagged",
            ),
        ],
    )
    def test_lg_node_001(self, tmp_project: Path, code: str, should_flag: bool) -> None:
        payload = self.posttool_payload(tmp_project, "graph/nodes.py", code)
        result = evaluate_payload(payload)
        finding = next((f for f in result.findings if f.rule_id == "LG-NODE-001"), None)
        assert (not should_flag and finding is None) or (
            should_flag and finding is not None and finding.decision is None
        ), f"Unexpected LG-NODE-001 result for code:\n{code}"

    def test_non_graph_file_ignored(self, tmp_project: Path) -> None:
        code = "from typing import TypedDict\nclass Config(TypedDict):\n    items: list[str]\n"
        payload = self.posttool_payload(tmp_project, "utils/helpers.py", code)
        result = evaluate_payload(payload)
        lg_findings = [f for f in result.findings if f.rule_id.startswith("LG-")]
        assert not lg_findings

    def test_set_entry_point_flagged(self, tmp_project: Path) -> None:
        code = (
            "from langgraph.graph import StateGraph\n"
            "graph = StateGraph(MyState)\n"
            'graph.set_entry_point("start")\n'
        )
        payload = self.posttool_payload(tmp_project, "builder.py", code)
        result = evaluate_payload(payload)
        findings = [f for f in result.findings if f.rule_id == "LG-API-001"]
        assert findings
        assert "add_edge(START" in (findings[0].additional_context or "")

    def test_add_edge_start_not_flagged(self, tmp_project: Path) -> None:
        code = (
            "from langgraph.graph import START, StateGraph\n"
            "graph = StateGraph(MyState)\n"
            'graph.add_edge(START, "start")\n'
        )
        payload = self.posttool_payload(tmp_project, "builder.py", code)
        result = evaluate_payload(payload)
        api_findings = [f for f in result.findings if f.rule_id == "LG-API-001"]
        assert not api_findings

    def test_all_lg_findings_are_advisory(self, tmp_project: Path) -> None:
        code = (
            "from typing import TypedDict\nfrom langgraph.graph import StateGraph\n"
            "class BadState(TypedDict):\n    items: list[str]\n\n"
            'def bad_node(state):\n    state["items"].append("x")\n    return state\n'
        )
        payload = self.posttool_payload(tmp_project, "graph/bad.py", code)
        result = evaluate_payload(payload)
        lg_findings = [f for f in result.findings if f.rule_id.startswith("LG-")]
        assert lg_findings
        non_advisory = [f.rule_id for f in lg_findings if f.decision is not None]
        assert not non_advisory, f"These LG findings must be advisory: {non_advisory}"
        missing_ctx = [f.rule_id for f in lg_findings if f.additional_context is None]
        assert not missing_ctx, (
            f"These LG findings lack additional_context: {missing_ctx}"
        )

    def test_node_detected_via_pyproject(self, tmp_project: Path) -> None:
        """State mutation detected even without langgraph import, via pyproject.toml."""
        code = 'def process(state):\n    state["results"].append("done")\n    return state\n'
        (tmp_project / "graph").mkdir(exist_ok=True)
        _ = (tmp_project / "graph" / "nodes.py").write_text(code)
        _ = (tmp_project / "pyproject.toml").write_text(
            '[project]\nname = "my-agent"\ndependencies = ["langgraph>=0.2"]\n'
        )
        payload: ObjectDict = {
            "session_id": "t",
            "cwd": str(tmp_project),
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "graph/nodes.py", "content": code},
            "tool_response": {"filePath": "graph/nodes.py", "success": True},
        }
        result = evaluate_payload(payload)
        assert any(f.rule_id == "LG-NODE-001" for f in result.findings)

    def test_node_without_pyproject_ignored(self, tmp_project: Path) -> None:
        code = 'def process(state):\n    state["results"].append("done")\n    return state\n'
        (tmp_project / "graph").mkdir(exist_ok=True)
        _ = (tmp_project / "graph" / "nodes.py").write_text(code)
        # No pyproject.toml
        payload: ObjectDict = {
            "session_id": "t",
            "cwd": str(tmp_project),
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "graph/nodes.py", "content": code},
            "tool_response": {"filePath": "graph/nodes.py", "success": True},
        }
        result = evaluate_payload(payload)
        lg_findings = [f for f in result.findings if f.rule_id.startswith("LG-")]
        assert not lg_findings


@pytest.mark.parametrize(
    "code, should_deny",
    [
        ("import logging\nlogger = logging.getLogger(__name__)\n", True),
        ("from logging import StreamHandler\n", True),
        ("logging.getLogger('myapp')\n", True),
        ("import structlog\nlog = structlog.get_logger()\n", False),
        ("# logging is disabled\nprint('hello')\n", False),
    ],
)
def test_py_log_001(pretool_write: WriteBuilder, code: str, should_deny: bool) -> None:
    result = evaluate_payload(pretool_write("src/app.py", code))
    ids = finding_ids(result)
    assert ("PY-LOG-001" in ids) is should_deny, (
        f"Unexpected PY-LOG-001 result for code:\n{code}"
    )


@pytest.mark.parametrize(
    "code, should_deny",
    [
        ("x = foo()  # type: ignore\n", True),
        ("x = foo()  # type: ignore[arg-type]\n", True),
        ("x = foo()  # noqa\n", True),
        ("x = foo()  # noqa: E501\n", True),
        ("x = foo()  # ruff: noqa\n", True),
        ("x = foo()  # pylint: disable=C0114\n", True),
        ("x = foo()  # pyright: ignore\n", True),
        ("x = foo()  # pyre-ignore\n", True),
        ("x = foo()  # ty: ignore\n", True),
        ("x = foo()  # ty: ignore[possibly-unbound]\n", True),
        ("x = foo()  # this is fine\n", False),
    ],
)
def test_py_type_002(pretool_write: WriteBuilder, code: str, should_deny: bool) -> None:
    result = evaluate_payload(pretool_write("src/module.py", code))
    ids = finding_ids(result)
    assert ("PY-TYPE-002" in ids) is should_deny, (
        f"Unexpected PY-TYPE-002 result for code:\n{code}"
    )


class TestCommentedOutCode:
    def test_two_commented_lines_denied(self, pretool_write: WriteBuilder) -> None:
        code = "# def old_func():\n# import os\nx = 1\n"
        result = evaluate_payload(pretool_write("src/clean.py", code))
        assert "PY-QUALITY-008" in finding_ids(result)

    def test_single_comment_allowed(self, pretool_write: WriteBuilder) -> None:
        code = "# def old_func():\nx = 1\n"
        result = evaluate_payload(pretool_write("src/clean.py", code))
        assert "PY-QUALITY-008" not in finding_ids(result)

    def test_docstring_comment_allowed(self, pretool_write: WriteBuilder) -> None:
        code = "# This module handles user authentication.\n# It should be imported early.\nx = 1\n"
        result = evaluate_payload(pretool_write("src/auth.py", code))
        assert "PY-QUALITY-008" not in finding_ids(result)


@pytest.mark.parametrize(
    "code, should_deny",
    [
        ("path = '/home/trav/data/file.txt'\n", True),
        ("path = '/Users/admin/Desktop/file.txt'\n", True),
        ("path = '/tmp/mydata/cache.db'\n", True),
        ("path = Path(__file__).parent / 'data'\n", False),
        ("path = '/tmp/x'\n", False),
    ],
)
def test_py_quality_009(
    pretool_write: WriteBuilder, code: str, should_deny: bool
) -> None:
    result = evaluate_payload(pretool_write("src/config.py", code))
    ids = finding_ids(result)
    assert ("PY-QUALITY-009" in ids) is should_deny, (
        f"Unexpected PY-QUALITY-009 result for code:\n{code}"
    )
