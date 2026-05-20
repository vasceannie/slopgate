from __future__ import annotations

import ast
from typing import TYPE_CHECKING, final

from typing_extensions import override

from vibeforcer.models import RuleFinding, Severity
from vibeforcer.rules.base import Rule

from ._helpers import decision_for_context, evaluate_common, parse_module
from ._pytest_asyncio_config import (
    pytest_asyncio_default_fixture_loop_scope,
    pytest_asyncio_mode,
)
from ._pytest_asyncio_ast import (
    FixtureCheckTarget,
    fixture_decorator_call,
    fixture_decorator_name,
    has_async_backend_mark,
    has_async_yield,
    iter_async_tests,
    pytest_aliases,
    string_keyword,
)
from ._pytest_asyncio_messages import PYTEST_ASYNCIO_TEMPLATE
from ._pytest_asyncio_scope import (
    fixture_scope_fragment,
    is_unknown_fixture_scope,
    is_valid_fixture_loop_scope,
    valid_fixture_scope_text,
)

if TYPE_CHECKING:
    from vibeforcer.context import HookContext


def _is_pytest_path(path_value: str) -> bool:
    normalized = path_value.replace("\\", "/").lower()
    name = normalized.rsplit("/", 1)[-1]
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
        or normalized.startswith("tests/")
        or "/tests/" in normalized
    )


def _is_auto_mode(ctx: HookContext) -> bool:
    return pytest_asyncio_mode(ctx) == "auto"


def _unknown_fixture_scope_message(target: FixtureCheckTarget, scope: str | None) -> str:
    return (
        f"Unknown pytest-asyncio fixture scope `{scope}` on async fixture "
        f"`{target.node.name}` in `{target.path_value}`. Valid fixture `scope` "
        f"values are {valid_fixture_scope_text()}."
    )


def _unknown_loop_scope_message(
    target: FixtureCheckTarget,
    scope_source: str,
    effective_loop_scope: str | None,
) -> str:
    return (
        f"Unknown pytest-asyncio fixture {scope_source} `{effective_loop_scope}` "
        f"for async fixture `{target.node.name}` in `{target.path_value}`. Valid "
        f"fixture loop scope values are {valid_fixture_scope_text()}."
    )


def _configured_loop_scope_note(
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


def _resource_scope_note(node: ast.AsyncFunctionDef) -> str:
    if has_async_yield(node):
        return " For async-yield resource fixtures, match loop scope to fixture lifetime."
    return ""


def _plain_auto_fixture_scope_message(
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
        f"Use `@pytest_asyncio.fixture(scope=\"{fixture_scope}\", "
        f"loop_scope=\"{fixture_scope}\")` or set "
        f"`asyncio_default_fixture_loop_scope = {fixture_scope}` in pytest config."
        f"{configured_note}{resource_note}"
    )


def _explicit_fixture_loop_scope_message(
    target: FixtureCheckTarget,
    *,
    fixture_scope: str,
    configured_note: str,
    resource_note: str,
) -> str:
    return (
        f"{fixture_scope_fragment(fixture_scope).title()} async fixture `{target.node.name}` "
        f"in `{target.path_value}` should declare `loop_scope=\"{fixture_scope}\"` "
        "or broader so the event-loop lifetime is explicit. pytest-asyncio "
        "requires any configured fixture event-loop scope to be the same as "
        "or broader than its fixture cache scope; an explicit "
        "`asyncio_default_fixture_loop_scope` pytest config value can satisfy "
        "this too."
        f"{configured_note}{resource_note}"
    )


@final
class PythonPytestAsyncioRule(Rule):
    """Guide agent-generated async pytest code toward config-aware pytest-asyncio patterns."""

    rule_id = "PY-TEST-005"
    title = "Guide pytest-asyncio test patterns"
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

    def _finding(
        self,
        ctx: HookContext,
        path_value: str,
        node: ast.AsyncFunctionDef,
        message: str,
    ) -> RuleFinding:
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.MEDIUM,
            decision=decision_for_context(ctx),
            message=message,
            additional_context=PYTEST_ASYNCIO_TEMPLATE,
            metadata={
                "path": path_value,
                "function": node.name,
                "line": node.lineno,
                "asyncio_mode": pytest_asyncio_mode(ctx) or "strict-default",
            },
        )

    def _check_async_tests(
        self,
        module: ast.Module,
        path_value: str,
        ctx: HookContext,
    ) -> list[RuleFinding]:
        if _is_auto_mode(ctx):
            return []
        findings: list[RuleFinding] = []
        aliases = pytest_aliases(module)
        for candidate in iter_async_tests(module):
            node = candidate.node
            if candidate.has_context_mark or has_async_backend_mark(node.decorator_list, aliases):
                continue
            findings.append(self._finding(
                ctx,
                path_value,
                node,
                (
                    f"Async pytest test `{node.name}` in `{path_value}` needs "
                    "`@pytest.mark.asyncio` in default/strict pytest-asyncio mode. "
                    "If maintainers intentionally want auto mode, confirm that policy "
                    "and set `asyncio_mode = auto` in pytest config instead of relying "
                    "on implicit behavior."
                ),
            ))
        return findings

    def _check_plain_async_fixture(
        self,
        ctx: HookContext,
        path_value: str,
        node: ast.AsyncFunctionDef,
    ) -> RuleFinding | None:
        if _is_auto_mode(ctx):
            return None
        return self._finding(
            ctx,
            path_value,
            node,
            (
                f"Async pytest fixture `{node.name}` in `{path_value}` uses "
                "plain `@pytest.fixture`. Use `@pytest_asyncio.fixture` in "
                "default/strict pytest-asyncio mode, or confirm with maintainers "
                "before explicitly setting `asyncio_mode = auto` in pytest config."
            ),
        )

    def _check_fixture_loop_scope(
        self,
        ctx: HookContext,
        target: FixtureCheckTarget,
    ) -> RuleFinding | None:
        node = target.node
        fixture_name = fixture_decorator_name(node, target.aliases)
        scope = string_keyword(target.call, "scope") if target.call is not None else None
        loop_scope = string_keyword(target.call, "loop_scope") if target.call is not None else None
        configured_loop_scope = pytest_asyncio_default_fixture_loop_scope(ctx)
        effective_loop_scope = loop_scope or configured_loop_scope
        if is_unknown_fixture_scope(scope):
            return self._finding(ctx, target.path_value, node, _unknown_fixture_scope_message(target, scope))
        if is_unknown_fixture_scope(effective_loop_scope):
            scope_source = "loop_scope" if loop_scope is not None else "asyncio_default_fixture_loop_scope"
            message = _unknown_loop_scope_message(target, scope_source, effective_loop_scope)
            return self._finding(ctx, target.path_value, node, message)
        if is_valid_fixture_loop_scope(scope, effective_loop_scope):
            return None
        fixture_scope = scope or "function"
        configured_note = _configured_loop_scope_note(
            configured_loop_scope=configured_loop_scope,
            loop_scope=loop_scope,
            fixture_scope=fixture_scope,
        )
        resource_note = _resource_scope_note(node)
        if fixture_name == "pytest.fixture":
            message = _plain_auto_fixture_scope_message(
                target,
                fixture_scope=fixture_scope,
                configured_note=configured_note,
                resource_note=resource_note,
            )
            return self._finding(ctx, target.path_value, node, message)
        message = _explicit_fixture_loop_scope_message(
            target,
            fixture_scope=fixture_scope,
            configured_note=configured_note,
            resource_note=resource_note,
        )
        return self._finding(ctx, target.path_value, node, message)

    def _check_async_fixtures(
        self,
        module: ast.Module,
        path_value: str,
        ctx: HookContext,
    ) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        aliases = pytest_aliases(module)
        for node in ast.walk(module):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            fixture_name = fixture_decorator_name(node, aliases)
            if fixture_name is None:
                continue
            plain_fixture_finding = None
            if fixture_name == "pytest.fixture":
                plain_fixture_finding = self._check_plain_async_fixture(ctx, path_value, node)
            if plain_fixture_finding is not None:
                findings.append(plain_fixture_finding)
                continue
            call = fixture_decorator_call(node, aliases)
            target = FixtureCheckTarget(path_value, node, call, aliases)
            loop_scope_finding = self._check_fixture_loop_scope(ctx, target)
            if loop_scope_finding is not None:
                findings.append(loop_scope_finding)
        return findings

    def _check_source(
        self,
        source: str,
        path_value: str,
        ctx: HookContext,
    ) -> list[RuleFinding]:
        if not _is_pytest_path(path_value):
            return []
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        findings = self._check_async_tests(module, path_value, ctx)
        findings.extend(self._check_async_fixtures(module, path_value, ctx))
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        return evaluate_common(self, ctx, self._check_source)
