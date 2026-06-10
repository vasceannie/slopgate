from __future__ import annotations

import ast
from typing import TYPE_CHECKING, final

from typing_extensions import override

from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule

from ._helpers import decision_for_context, evaluate_common, parse_module
from ._pytest_asyncio_config import pytest_asyncio_mode
from ._pytest_asyncio_fixture_scope import (
    configured_loop_scope_note,
    explicit_fixture_loop_scope_message,
    fixture_scope_state,
    is_pytest_path,
    plain_auto_fixture_scope_message,
    resource_scope_note,
    unknown_fixture_scope_message,
    unknown_loop_scope_message,
)
from ._pytest_asyncio_ast import (
    FixtureCheckTarget,
    fixture_decorator_call,
    fixture_decorator_name,
    has_async_backend_mark,
    iter_async_tests,
    pytest_aliases,
)
from ._pytest_asyncio_messages import PYTEST_ASYNCIO_TEMPLATE
from ._pytest_asyncio_scope import (
    is_unknown_fixture_scope,
    is_valid_fixture_loop_scope,
)

if TYPE_CHECKING:
    from slopgate.context import HookContext


def _is_auto_mode(ctx: HookContext) -> bool:
    return pytest_asyncio_mode(ctx) == "auto"


@final
class PythonPytestAsyncioRule(Rule):
    """Guide agent-generated async pytest code toward config-aware pytest-asyncio patterns."""

    rule_id = "PY-TEST-005"
    title = "Guide pytest-asyncio test patterns"
    events = ("PreToolUse", "PermissionRequest", "PostToolUse")

    def finding(
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
            if candidate.has_context_mark or has_async_backend_mark(
                node.decorator_list, aliases
            ):
                continue
            findings.append(
                self.finding(
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
                )
            )
        return findings

    def _check_plain_async_fixture(
        self,
        ctx: HookContext,
        path_value: str,
        node: ast.AsyncFunctionDef,
    ) -> RuleFinding | None:
        if _is_auto_mode(ctx):
            return None
        return self.finding(
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
        state = fixture_scope_state(ctx, target)
        scope = state.scope
        loop_scope = state.loop_scope
        configured_loop_scope = state.configured_loop_scope
        effective_loop_scope = state.effective_loop_scope
        fixture_name = state.fixture_name
        if is_unknown_fixture_scope(scope):
            return self.finding(
                ctx,
                target.path_value,
                node,
                unknown_fixture_scope_message(target, scope),
            )
        if is_unknown_fixture_scope(effective_loop_scope):
            scope_source = (
                "loop_scope"
                if loop_scope is not None
                else "asyncio_default_fixture_loop_scope"
            )
            message = unknown_loop_scope_message(
                target, scope_source, effective_loop_scope
            )
            return self.finding(ctx, target.path_value, node, message)
        if is_valid_fixture_loop_scope(scope, effective_loop_scope):
            return None
        fixture_scope = scope or "function"
        configured_note = configured_loop_scope_note(
            configured_loop_scope=configured_loop_scope,
            loop_scope=loop_scope,
            fixture_scope=fixture_scope,
        )
        resource_note = resource_scope_note(node)
        if fixture_name == "pytest.fixture":
            message = plain_auto_fixture_scope_message(
                target,
                fixture_scope=fixture_scope,
                configured_note=configured_note,
                resource_note=resource_note,
            )
            return self.finding(ctx, target.path_value, node, message)
        message = explicit_fixture_loop_scope_message(
            target,
            fixture_scope=fixture_scope,
            configured_note=configured_note,
            resource_note=resource_note,
        )
        return self.finding(ctx, target.path_value, node, message)

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
                plain_fixture_finding = self._check_plain_async_fixture(
                    ctx, path_value, node
                )
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
        if not is_pytest_path(path_value):
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
