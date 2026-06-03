from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

from hypothesis import given, strategies

from tests.test_enrichment_public_api import context_for_source
from vibeforcer.rules.python_ast._pytest_asyncio_ast import (
    FixtureCheckTarget,
    fixture_decorator_call,
    fixture_decorator_name,
    has_async_backend_mark,
    has_async_yield,
    iter_async_tests,
    pytest_aliases,
    string_keyword,
)
from vibeforcer.rules.python_ast._pytest_asyncio_config import (
    pytest_asyncio_default_fixture_loop_scope,
    pytest_asyncio_mode,
)
from vibeforcer.rules.python_ast._pytest_asyncio_scope import (
    fixture_scope_fragment,
    is_unknown_fixture_scope,
    is_valid_fixture_loop_scope,
    valid_fixture_scope_text,
)

SCOPE_VALUES = strategies.sampled_from(
    [None, "function", "class", "module", "package", "session", "nonsense"]
)


def first_async_function(source: str) -> ast.AsyncFunctionDef:
    module = ast.parse(source)
    return next(node for node in module.body if isinstance(node, ast.AsyncFunctionDef))


def test_pytest_asyncio_ast_helpers_detect_aliases_and_marked_tests() -> None:
    module = ast.parse(
        "import pytest as pt\n"
        "import pytest_asyncio as pa\n"
        "@pt.mark.anyio\n"
        "async def test_with_backend():\n"
        "    pass\n"
        "@pa.fixture(loop_scope='module')\n"
        "async def resource():\n"
        "    yield 'value'\n"
    )
    aliases = pytest_aliases(module)

    assert {
        "aliases": aliases,
        "async_tests": [candidate.node.name for candidate in iter_async_tests(module)],
        "backend_mark": has_async_backend_mark(module.body[2].decorator_list, aliases),
    } == {
        "aliases": {"pt": "pytest", "pa": "pytest_asyncio"},
        "async_tests": ["test_with_backend"],
        "backend_mark": True,
    }


def test_pytest_asyncio_ast_helpers_detect_fixture_decorator_details() -> None:
    module = ast.parse(
        "import pytest_asyncio as pa\n"
        "@pa.fixture(loop_scope='module')\n"
        "async def resource():\n"
        "    yield 'value'\n"
    )
    aliases = pytest_aliases(module)
    fixture_node = module.body[1]
    call = fixture_decorator_call(fixture_node, aliases)

    assert {
        "fixture_name": fixture_decorator_name(fixture_node, aliases),
        "loop_scope": string_keyword(call, "loop_scope") if call else None,
        "async_yield": has_async_yield(fixture_node),
    } == {
        "fixture_name": "pytest_asyncio.fixture",
        "loop_scope": "module",
        "async_yield": True,
    }


def test_fixture_check_target_preserves_ast_context() -> None:
    module = ast.parse("@pytest.fixture\nasync def resource():\n    pass\n")
    node = module.body[0]
    target = FixtureCheckTarget("test_sample.py", node, None, {"pytest": "pytest"})

    assert {
        "path": target.path_value,
        "name": target.node.name,
        "call": target.call,
        "aliases": target.aliases,
    } == {
        "path": "test_sample.py",
        "name": "resource",
        "call": None,
        "aliases": {"pytest": "pytest"},
    }


def test_pytest_asyncio_config_reads_pytest_ini(tmp_path: Path) -> None:
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\n"
        "asyncio_mode = auto\n"
        "asyncio_default_fixture_loop_scope = module\n",
        encoding="utf-8",
    )
    ctx = context_for_source(tmp_path, "")
    ctx = replace(ctx, config=replace(ctx.config, repo_root=tmp_path))

    assert {
        "mode": pytest_asyncio_mode(ctx),
        "loop_scope": pytest_asyncio_default_fixture_loop_scope(ctx),
    } == {
        "mode": "auto",
        "loop_scope": "module",
    }


@given(SCOPE_VALUES, SCOPE_VALUES)
def test_fixture_scope_ordering_property(
    scope: str | None,
    loop_scope: str | None,
) -> None:
    valid = is_valid_fixture_loop_scope(scope, loop_scope)
    unknown = is_unknown_fixture_scope(scope) or is_unknown_fixture_scope(loop_scope)

    assert {
        "unknown_invalid": (not valid) if unknown else True,
        "fragment": fixture_scope_fragment(scope).endswith("-scoped"),
        "valid_text_mentions_function": "function" in valid_fixture_scope_text(),
    } == {
        "unknown_invalid": True,
        "fragment": True,
        "valid_text_mentions_function": True,
    }


@given(strategies.text(alphabet="abcxyz_", min_size=1, max_size=12))
def test_string_keyword_ignores_missing_keyword_property(keyword_name: str) -> None:
    node = first_async_function("@pytest.fixture(scope='module')\nasync def x():\n    pass\n")
    call = fixture_decorator_call(node, {"pytest": "pytest"})

    assert {
        "missing": string_keyword(call, keyword_name) if call else None,
    } == {
        "missing": None if keyword_name != "scope" else "module",
    }
