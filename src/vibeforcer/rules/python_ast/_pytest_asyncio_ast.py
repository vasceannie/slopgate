from __future__ import annotations

import ast
from typing import NamedTuple


class _AsyncTestCandidate(NamedTuple):
    node: ast.AsyncFunctionDef
    has_context_mark: bool


class FixtureCheckTarget(NamedTuple):
    path_value: str
    node: ast.AsyncFunctionDef
    call: ast.Call | None
    aliases: dict[str, str]


def pytest_aliases(module: ast.Module) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for statement in module.body:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.name in {"pytest", "pytest_asyncio"}:
                    aliases[alias.asname or alias.name] = alias.name
        elif isinstance(statement, ast.ImportFrom) and statement.module in {"pytest", "pytest_asyncio"}:
            for alias in statement.names:
                if alias.name in {"mark", "fixture"}:
                    aliases[alias.asname or alias.name] = f"{statement.module}.{alias.name}"
    return aliases


def _decorator_call(decorator: ast.AST) -> ast.AST:
    if isinstance(decorator, ast.Call):
        return decorator.func
    return decorator


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        if prefix is None:
            return node.attr
        return f"{prefix}.{node.attr}"
    return None


def _resolve_alias(name: str | None, aliases: dict[str, str]) -> str | None:
    if name is None:
        return None
    head, separator, tail = name.partition(".")
    resolved = aliases.get(head)
    if resolved is None:
        return name
    return f"{resolved}{separator}{tail}" if separator else resolved


def _decorator_name(decorator: ast.expr, aliases: dict[str, str]) -> str | None:
    return _resolve_alias(_dotted_name(_decorator_call(decorator)), aliases)


_ASYNC_TEST_MARKS = {"pytest.mark.asyncio", "pytest.mark.anyio", "pytest.mark.trio"}


def _is_async_backend_mark(node: ast.AST, aliases: dict[str, str]) -> bool:
    return _resolve_alias(_dotted_name(_decorator_call(node)), aliases) in _ASYNC_TEST_MARKS


def has_async_backend_mark(decorators: list[ast.expr], aliases: dict[str, str]) -> bool:
    return any(_is_async_backend_mark(decorator, aliases) for decorator in decorators)


def _pytestmark_value_has_async_backend(value: ast.AST, aliases: dict[str, str]) -> bool:
    if _is_async_backend_mark(value, aliases):
        return True
    if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return any(_pytestmark_value_has_async_backend(item, aliases) for item in value.elts)
    return False


def _body_has_asyncio_pytestmark(body: list[ast.stmt], aliases: dict[str, str]) -> bool:
    for statement in body:
        if not isinstance(statement, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in statement.targets):
            continue
        if _pytestmark_value_has_async_backend(statement.value, aliases):
            return True
    return False


def _is_collected_pytest_class(node: ast.ClassDef) -> bool:
    if not node.name.startswith("Test"):
        return False
    return not any(
        isinstance(child, ast.FunctionDef) and child.name in {"__init__", "__new__"}
        for child in node.body
    )


def iter_async_tests(module: ast.Module) -> list[_AsyncTestCandidate]:
    candidates: list[_AsyncTestCandidate] = []
    aliases = pytest_aliases(module)
    module_mark = _body_has_asyncio_pytestmark(module.body, aliases)
    for statement in module.body:
        if isinstance(statement, ast.AsyncFunctionDef) and statement.name.startswith("test_"):
            if fixture_decorator_name(statement, aliases) is None:
                candidates.append(_AsyncTestCandidate(statement, module_mark))
        if not isinstance(statement, ast.ClassDef) or not _is_collected_pytest_class(statement):
            continue
        class_mark = has_async_backend_mark(
            statement.decorator_list, aliases
        ) or _body_has_asyncio_pytestmark(statement.body, aliases)
        for child in statement.body:
            if not isinstance(child, ast.AsyncFunctionDef) or not child.name.startswith("test_"):
                continue
            if fixture_decorator_name(child, aliases) is None:
                candidates.append(_AsyncTestCandidate(child, module_mark or class_mark))
    return candidates


def fixture_decorator_name(node: ast.AsyncFunctionDef, aliases: dict[str, str]) -> str | None:
    for decorator in node.decorator_list:
        name = _decorator_name(decorator, aliases)
        if name in {"pytest.fixture", "pytest_asyncio.fixture"}:
            return name
    return None


def fixture_decorator_call(node: ast.AsyncFunctionDef, aliases: dict[str, str]) -> ast.Call | None:
    for decorator in node.decorator_list:
        if (
            _decorator_name(decorator, aliases) in {"pytest.fixture", "pytest_asyncio.fixture"}
            and isinstance(decorator, ast.Call)
        ):
            return decorator
    return None


def string_keyword(call: ast.Call, keyword_name: str) -> str | None:
    for keyword in call.keywords:
        if keyword.arg != keyword_name:
            continue
        value = keyword.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value.strip().lower()
    return None


def has_async_yield(node: ast.AsyncFunctionDef) -> bool:
    return any(isinstance(child, (ast.Yield, ast.YieldFrom)) for child in ast.walk(node))


