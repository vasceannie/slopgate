from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate.lint._collectors import run_all_collectors
from slopgate.lint._config import load_config, reset_config


def _feature_envy_source(project_root: Path) -> Path:
    source_file = project_root / "src" / "app.py"
    source_file.parent.mkdir(exist_ok=True)
    source_file.write_text(
        "\n".join(
            [
                "def render():",
                "    customer = account.customer.name",
                "    total = account.invoice.total",
                "    status = account.state.value",
                "    return f'{customer}:{total}:{status}'",
            ]
        ),
        encoding="utf-8",
    )
    return source_file


def _noncanonical_import_alias_source(project_root: Path) -> Path:
    source_file = project_root / "src" / "imports.py"
    source_file.parent.mkdir(exist_ok=True)
    source_file.write_text("import requests as rq\n", encoding="utf-8")
    return source_file


def _unlogged_boundary_source(project_root: Path) -> Path:
    source_file = project_root / "src" / "events" / "publisher.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        "\n".join(
            [
                "def publish_user_created(event):",
                "    bus.publish(event)",
            ]
        ),
        encoding="utf-8",
    )
    return source_file


def _unmarked_async_test_source(project_root: Path) -> Path:
    source_file = project_root / "tests" / "test_async_user.py"
    source_file.parent.mkdir(exist_ok=True)
    source_file.write_text(
        "\n".join(
            [
                "async def test_fetches_user():",
                "    assert await fetch_user()",
            ]
        ),
        encoding="utf-8",
    )
    return source_file


def _langgraph_source(project_root: Path) -> Path:
    source_file = project_root / "src" / "graph" / "workflow.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        "\n".join(
            [
                "from typing import TypedDict",
                "from langgraph.graph import StateGraph",
                "",
                "class AgentState(TypedDict):",
                "    messages: list[str]",
                "",
                "def node(state):",
                "    state['messages'].append('hello')",
                "    return state",
                "",
                "graph = StateGraph(AgentState)",
                "graph.set_entry_point('node')",
            ]
        ),
        encoding="utf-8",
    )
    return source_file


def _collector_counts(project_root: Path, source_file: Path) -> dict[str, int]:
    load_config(project_root)
    rel = source_file.relative_to(project_root).as_posix()
    src_files = [] if rel.startswith("tests/") else [source_file]
    test_files = [source_file] if rel.startswith("tests/") else []
    return {
        name: len(violations)
        for name, violations in run_all_collectors(src_files, test_files)
    }


def _enable_cli_surface(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    rule_id: str,
) -> None:
    config_path = config_dir / "config.json"
    config_path.write_text(
        json.dumps({"rule_surfaces": {rule_id: {"cli": {"enabled": True}}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SLOPGATE_CONFIG", str(config_path))
    reset_config()


def test_new_interoperable_collectors_require_explicit_cli_surface_enablement(
    tmp_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_file = _feature_envy_source(tmp_project)
    reset_config()
    disabled_collectors = _collector_counts(tmp_project, source_file)

    _enable_cli_surface(tmp_path, monkeypatch, "PY-CODE-012")
    enabled_collectors = _collector_counts(tmp_project, source_file)

    assert "feature-envy" not in disabled_collectors, (
        "New advisory CLI counterparts should default off until a surface enables them"
    )
    assert enabled_collectors["feature-envy"] == 1, (
        "PY-CODE-012 cli surface should enable the feature-envy batch collector"
    )


def test_import_hook_rule_counterpart_requires_cli_surface_enablement(
    tmp_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_file = _noncanonical_import_alias_source(tmp_project)
    reset_config()
    disabled_collectors = _collector_counts(tmp_project, source_file)

    _enable_cli_surface(tmp_path, monkeypatch, "PY-IMPORT-002")
    enabled_collectors = _collector_counts(tmp_project, source_file)

    assert "import-alias" not in disabled_collectors, (
        "New import CLI counterparts should default off until a surface enables them"
    )
    assert enabled_collectors["import-alias"] == 1, (
        "PY-IMPORT-002 cli surface should enable the import-alias batch collector"
    )


def test_boundary_logging_counterpart_requires_cli_surface_enablement(
    tmp_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_file = _unlogged_boundary_source(tmp_project)
    reset_config()
    disabled_collectors = _collector_counts(tmp_project, source_file)

    _enable_cli_surface(tmp_path, monkeypatch, "PY-LOG-002")
    enabled_collectors = _collector_counts(tmp_project, source_file)

    assert "boundary-logging" not in disabled_collectors, (
        "Boundary logging CLI counterpart should default off until enabled"
    )
    assert enabled_collectors["boundary-logging"] == 1, (
        "PY-LOG-002 cli surface should enable the boundary-logging collector"
    )


def test_pytest_asyncio_counterpart_requires_cli_surface_enablement(
    tmp_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_file = _unmarked_async_test_source(tmp_project)
    reset_config()
    disabled_collectors = _collector_counts(tmp_project, test_file)

    _enable_cli_surface(tmp_path, monkeypatch, "PY-TEST-005")
    enabled_collectors = _collector_counts(tmp_project, test_file)

    assert "pytest-asyncio-pattern" not in disabled_collectors, (
        "PY-TEST-005 CLI counterpart should default off until enabled"
    )
    assert enabled_collectors["pytest-asyncio-pattern"] == 1, (
        "PY-TEST-005 cli surface should enable the pytest-asyncio collector"
    )


@pytest.mark.parametrize(
    ("rule_id", "collector"),
    [
        ("LG-API-001", "langgraph-deprecated-api"),
        ("LG-NODE-001", "langgraph-state-mutation"),
        ("LG-STATE-001", "langgraph-state-reducer"),
    ],
)
def test_langgraph_counterparts_require_cli_surface_enablement(
    tmp_project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rule_id: str,
    collector: str,
) -> None:
    source_file = _langgraph_source(tmp_project)
    reset_config()
    disabled_collectors = _collector_counts(tmp_project, source_file)

    _enable_cli_surface(tmp_path, monkeypatch, rule_id)
    enabled_collectors = _collector_counts(tmp_project, source_file)

    assert collector not in disabled_collectors, (
        f"{rule_id} CLI counterpart should default off until enabled"
    )
    assert enabled_collectors[collector] == 1, (
        f"{rule_id} cli surface should enable {collector}"
    )
