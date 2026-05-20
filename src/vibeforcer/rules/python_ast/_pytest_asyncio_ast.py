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


def _add_module_import_aliases(statement: ast.Import, aliases: dict[str, str]) -> None:
    for alias in statement.names:
        if alias.name in {"pytest", "pytest_asyncio"}:
            aliases[alias.asname or alias.name] = alias.name


def _add_from_import_aliases(statement: ast.ImportFrom, aliases: dict[str, str]) -> None:
    if statement.module not in {"pytest", "pytest_asyncio"}:
        return
    for alias in statement.names:
        if alias.name in {"mark", "fixture"}:
            aliases[alias.asname or alias.name] = f"{statement.module}.{alias.name}"


def pytest_aliases(module: ast.Module) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for statement in module.body:
        if isinstance(statement, ast.Import):
            _add_module_import_aliases(statement, aliases)
        elif isinstance(statement, ast.ImportFrom):
            _add_from_import_aliases(statement, aliases)
    return aliases


def _decorator_call(decorator: ast.AST) -> ast.AST:
    if isinstance(decorator, ast.Call):
        return decorator.func
    return decorator


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, (ast.Attribute, ast.Name)):
        return ast.unparse(node)
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
    return _decorator_name(node, aliases) in _ASYNC_TEST_MARKS


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


def _async_test_candidate(
    node: ast.AST,
    aliases: dict[str, str],
    *,
    has_context_mark: bool,
) -> _AsyncTestCandidate | None:
    if not isinstance(node, ast.AsyncFunctionDef) or not node.name.startswith("test_"):
        return None
    if fixture_decorator_name(node, aliases) is not None:
        return None
    return _AsyncTestCandidate(node, has_context_mark)


def _iter_class_async_tests(
    statement: ast.stmt,
    aliases: dict[str, str],
    *,
    module_mark: bool,
) -> list[_AsyncTestCandidate]:
    if not isinstance(statement, ast.ClassDef) or not _is_collected_pytest_class(statement):
        return []
    class_mark = has_async_backend_mark(
        statement.decorator_list, aliases
    ) or _body_has_asyncio_pytestmark(statement.body, aliases)
    candidates: list[_AsyncTestCandidate] = []
    for child in statement.body:
        candidate = _async_test_candidate(child, aliases, has_context_mark=module_mark or class_mark)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def iter_async_tests(module: ast.Module) -> list[_AsyncTestCandidate]:
    candidates: list[_AsyncTestCandidate] = []
    aliases = pytest_aliases(module)
    module_mark = _body_has_asyncio_pytestmark(module.body, aliases)
    for statement in module.body:
        candidate = _async_test_candidate(statement, aliases, has_context_mark=module_mark)
        if candidate is not None:
            candidates.append(candidate)
        candidates.extend(_iter_class_async_tests(statement, aliases, module_mark=module_mark))
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


