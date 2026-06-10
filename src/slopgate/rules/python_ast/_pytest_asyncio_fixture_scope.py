"""Fixture loop-scope resolution and guidance messages for pytest-asyncio."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING

from slopgate.rules.python_ast._pytest_asyncio_ast import (
    FixtureCheckTarget,
    fixture_decorator_name,
    has_async_yield,
    string_keyword,
)
from slopgate.rules.python_ast._pytest_asyncio_config import (
    pytest_asyncio_default_fixture_loop_scope,
)
from slopgate.rules.python_ast._pytest_asyncio_scope import (
    fixture_scope_fragment,
    valid_fixture_scope_text,
)

if TYPE_CHECKING:
    from slopgate.context import HookContext


def is_pytest_path(path_value: str) -> bool:
    normalized = path_value.replace("\\", "/").lower()
    name = normalized.rsplit("/", 1)[-1]
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
        or normalized.startswith("tests/")
        or "/tests/" in normalized
    )


def unknown_fixture_scope_message(
    target: FixtureCheckTarget, scope: str | None
) -> str:
    return (
        f"Unknown pytest-asyncio fixture scope `{scope}` on async fixture "
        f"`{target.node.name}` in `{target.path_value}`. Valid fixture `scope` "
        f"values are {valid_fixture_scope_text()}."
    )


def unknown_loop_scope_message(
    target: FixtureCheckTarget,
    scope_source: str,
    effective_loop_scope: str | None,
) -> str:
    return (
        f"Unknown pytest-asyncio fixture {scope_source} `{effective_loop_scope}` "
        f"for async fixture `{target.node.name}` in `{target.path_value}`. Valid "
        f"fixture loop scope values are {valid_fixture_scope_text()}."
    )


def configured_loop_scope_note(
    *,
    configured_loop_scope: str | None,
    loop_scope: str | None,
    fixture_scope: str,
) -> str:
    if loop_scope is not None or configured_loop_scope is None:
        return ""
    return (
        f" Current pytest config sets `asyncio_default_fixture_loop_scope = {configured_loop_scope}`, "
        f"which is narrower than the fixture's `{fixture_scope}` cache scope."
    )


def resource_scope_note(node: ast.AsyncFunctionDef) -> str:
    if has_async_yield(node):
        return (
            " For async-yield resource fixtures, match loop scope to fixture lifetime."
        )
    return ""


@dataclass(frozen=True)
class FixtureScopeState:
    fixture_name: str | None
    scope: str | None
    loop_scope: str | None
    configured_loop_scope: str | None
    effective_loop_scope: str | None


def fixture_scope_state(
    ctx: HookContext, target: FixtureCheckTarget
) -> FixtureScopeState:
    node = target.node
    fixture_name = fixture_decorator_name(node, target.aliases)
    scope = (
        string_keyword(target.call, "scope") if target.call is not None else None
    )
    loop_scope = (
        string_keyword(target.call, "loop_scope")
        if target.call is not None
        else None
    )
    configured_loop_scope = pytest_asyncio_default_fixture_loop_scope(ctx)
    return FixtureScopeState(
        fixture_name=fixture_name,
        scope=scope,
        loop_scope=loop_scope,
        configured_loop_scope=configured_loop_scope,
        effective_loop_scope=loop_scope or configured_loop_scope,
    )


def plain_auto_fixture_scope_message(
    target: FixtureCheckTarget,
    *,
    fixture_scope: str,
    configured_note: str,
    resource_note: str,
) -> str:
    return (
        f"{fixture_scope_fragment(fixture_scope).title()} async fixture `{target.node.name}` "
        f"in `{target.path_value}` is handled by `asyncio_mode = auto`, but broader "
        "fixture cache scope should declare an explicit pytest-asyncio loop scope "
        "so behavior is stable across pytest-asyncio versions. "
        f'Use `@pytest_asyncio.fixture(scope="{fixture_scope}", '
        f'loop_scope="{fixture_scope}")` or set '
        f"`asyncio_default_fixture_loop_scope = {fixture_scope}` in pytest config."
        f"{configured_note}{resource_note}"
    )


def explicit_fixture_loop_scope_message(
    target: FixtureCheckTarget,
    *,
    fixture_scope: str,
    configured_note: str,
    resource_note: str,
) -> str:
    return (
        f"{fixture_scope_fragment(fixture_scope).title()} async fixture `{target.node.name}` "
        f'in `{target.path_value}` should declare `loop_scope="{fixture_scope}"` '
        "or broader so the event-loop lifetime is explicit. pytest-asyncio "
        "requires any configured fixture event-loop scope to be the same as "
        "or broader than its fixture cache scope; an explicit "
        "`asyncio_default_fixture_loop_scope` pytest config value can satisfy "
        "this too."
        f"{configured_note}{resource_note}"
    )
