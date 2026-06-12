from __future__ import annotations

import ast
import importlib
from collections.abc import Callable, Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, strategies

from tests.test_enrichment_public_api import context_for_source

SHORT_TEXT = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789 _.-/", max_size=40
)

_pytest_asyncio_ast = importlib.import_module(
    "slopgate.rules.python_ast._pytest_asyncio_ast"
)
FixtureCheckTarget = getattr(_pytest_asyncio_ast, "FixtureCheckTarget")
fixture_decorator_call: Callable[..., ast.Call | None] = getattr(
    _pytest_asyncio_ast, "fixture_decorator_call"
)

_pytest_asyncio_fixture_scope = importlib.import_module(
    "slopgate.rules.python_ast._pytest_asyncio_fixture_scope"
)
configured_loop_scope_note: Callable[..., str] = getattr(
    _pytest_asyncio_fixture_scope, "configured_loop_scope_note"
)
fixture_scope_state: Callable[..., object] = getattr(
    _pytest_asyncio_fixture_scope, "fixture_scope_state"
)
is_pytest_path: Callable[[str], bool] = getattr(
    _pytest_asyncio_fixture_scope, "is_pytest_path"
)

_test_smell_rule_helpers = importlib.import_module(
    "slopgate.rules.python_ast._staging._test_smell_rule_helpers"
)
is_test_file: Callable[[str], bool] = getattr(_test_smell_rule_helpers, "is_test_file")
parse_test_module: Callable[..., ast.Module | None] = getattr(
    _test_smell_rule_helpers, "parse_test_module"
)
iter_test_module_nodes: Callable[..., Iterator[ast.AST]] = getattr(
    _test_smell_rule_helpers, "iter_test_module_nodes"
)


def _fixture_scope_state_for(scope: str) -> object:
    with TemporaryDirectory() as raw_path:
        source = (
            "import pytest\n"
            f"@pytest.fixture(scope={scope!r})\n"
            "async def resource():\n"
            "    pass\n"
        )
        module = ast.parse(source)
        node = next(
            item for item in module.body if isinstance(item, ast.AsyncFunctionDef)
        )
        aliases = {"pytest": "pytest"}
        target = FixtureCheckTarget(
            "tests/test_sample.py",
            node,
            fixture_decorator_call(node, aliases),
            aliases,
        )
        return fixture_scope_state(context_for_source(Path(raw_path), source), target)


@given(path=SHORT_TEXT)
def test_is_pytest_path_identifies_test_file_shapes_property(path: str) -> None:
    prefixed = f"tests/test_{path or 'sample'}.py"

    assert {"path": prefixed, "matched": is_pytest_path(prefixed)} == {
        "path": prefixed,
        "matched": True,
    }


@given(
    loop_scope=strategies.sampled_from(["function", "class", "module"]),
    fixture_scope=strategies.sampled_from(["module", "session"]),
)
def test_configured_loop_scope_note_mentions_effective_scopes_property(
    loop_scope: str,
    fixture_scope: str,
) -> None:
    note = configured_loop_scope_note(
        configured_loop_scope=loop_scope,
        loop_scope=None,
        fixture_scope=fixture_scope,
    )

    assert {"loop": loop_scope in note, "fixture": fixture_scope in note} == {
        "loop": True,
        "fixture": True,
    }


@given(scope=strategies.sampled_from(["function", "module", "session"]))
def test_fixture_scope_state_reads_fixture_decorator_property(scope: str) -> None:
    state = _fixture_scope_state_for(scope)

    assert getattr(state, "scope") == scope


@given(path=SHORT_TEXT)
def test_test_smell_path_helpers_agree_on_test_paths_property(path: str) -> None:
    test_path = f"tests/test_{path or 'sample'}.py"

    assert {"path": test_path, "matched": is_test_file(test_path)} == {
        "path": test_path,
        "matched": True,
    }


@given(is_test_path=strategies.booleans())
def test_parse_test_module_only_parses_test_paths_property(is_test_path: bool) -> None:
    source = "def test_sample():\n    assert True\n"
    path_value = "tests/test_sample.py" if is_test_path else "src/sample.py"
    with TemporaryDirectory() as raw_path:
        ctx = context_for_source(Path(raw_path), source, path=path_value)

        module = parse_test_module(source, path_value, ctx)
        nodes = list(iter_test_module_nodes(source, path_value, ctx))

    assert {"module": module is not None, "nodes": bool(nodes)} == {
        "module": is_test_path,
        "nodes": is_test_path,
    }
