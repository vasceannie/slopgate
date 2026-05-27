"""Detectors for code duplication."""

from __future__ import annotations

import ast
import copy
import hashlib
import sys
from collections import defaultdict
from collections.abc import Callable, Hashable
from pathlib import Path
from typing import TYPE_CHECKING, TypeGuard, TypeVar, cast
from typing_extensions import override
from vibeforcer.lint._baseline import Violation
from vibeforcer.lint._config import get_config
from vibeforcer.lint._helpers import (
    ParsedFile,
    ensure_parsed,
    find_source_files,
    function_body_lines,
)
if TYPE_CHECKING:
    pass


_BUILTINS = frozenset(
    {
        "len", "range", "print", "str", "int", "float", "bool", "list",
        "dict", "set", "tuple", "type", "isinstance", "issubclass",
        "hasattr", "getattr", "setattr", "delattr", "super", "property",
        "staticmethod", "classmethod", "enumerate", "zip", "map", "filter",
        "sorted", "reversed", "min", "max", "sum", "any", "all", "abs",
        "round", "repr", "hash", "id", "callable", "iter", "next", "open",
        "ValueError", "TypeError", "KeyError", "AttributeError", "RuntimeError",
        "NotImplementedError", "StopIteration", "Exception", "True", "False", "None",
    }
)

_SKIP_DECORATORS = frozenset({"abstractmethod", "overload", "property"})

_CONSTANT_TYPE_MAP: dict[type, str] = {
    bool: "BOOL",
    int: "INT",
    float: "FLOAT",
    str: "STR",
    bytes: "BYTES",
}


_ASTNodeT = TypeVar("_ASTNodeT", bound=ast.AST)


class _Normalizer(ast.NodeTransformer):
    """Transform an AST subtree into a canonical form for structural comparison."""

    def __init__(self) -> None:
        self._name_map: dict[str, str] = {}
        self.call_func_ids: set[int] = set()

    def _renamed(self, name: str) -> str:
        return self._name_map.setdefault(name, f"v{len(self._name_map)}")

    def _generic_visit_as(self, node: _ASTNodeT) -> _ASTNodeT:
        visited = self.generic_visit(node)
        if not isinstance(visited, type(node)):
            raise TypeError(f"expected {type(node).__name__} from generic_visit")
        return visited

    def _normalize_callable_signature(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        node.name = self._renamed(node.name)
        node.returns = None
        node.decorator_list = []

    @override
    def visit_Name(self, node: ast.Name) -> ast.Name:
        if id(node) not in self.call_func_ids and node.id not in _BUILTINS:
            node.id = self._renamed(node.id)
        return node

    @override
    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        # bool must be checked before int (bool is a subclass of int)
        for typ, token in _CONSTANT_TYPE_MAP.items():
            if isinstance(node.value, typ):
                node.value = token
                return node
        if node.value is None:
            node.value = "NONE"
        return node

    @override
    def visit_arg(self, node: ast.arg) -> ast.arg:
        node.arg = self._renamed(node.arg)
        node.annotation = None
        return self._generic_visit_as(node)

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self._normalize_callable_signature(node)
        return self._generic_visit_as(node)

    @override
    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> ast.AsyncFunctionDef:
        self._normalize_callable_signature(node)
        return self._generic_visit_as(node)


def _normalize_ast(node: ast.AST) -> str:
    """Produce a canonical string from an AST subtree."""
    tree = copy.deepcopy(node)
    normalizer = _Normalizer()
    for child in ast.walk(tree):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
            normalizer.call_func_ids.add(id(child.func))
    _ = cast(object, normalizer.visit(tree))
    _ = ast.fix_missing_locations(tree)
    return ast.dump(tree)


def _structure_hash(canonical: str) -> str:
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _is_import_stmt(stmt: ast.stmt) -> TypeGuard[ast.Import | ast.ImportFrom]:
    """Return True when *stmt* is a plain or from-import statement."""
    return isinstance(stmt, (ast.Import, ast.ImportFrom))


def _is_future_import(stmt: ast.stmt) -> bool:
    """Return True when *stmt* is ``from __future__ import ...``."""
    return isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__"



def _import_section(stmt: ast.Import | ast.ImportFrom) -> tuple[int, str]:
    """Classify import into (section-order, section-name)."""
    if _is_future_import(stmt):
        return 0, "future"
    if isinstance(stmt, ast.ImportFrom) and stmt.level > 0:
        return 3, "first-party"

    module_name = ""
    if isinstance(stmt, ast.ImportFrom):
        module_name = stmt.module or ""
    elif stmt.names:
        module_name = stmt.names[0].name

    top = module_name.split(".", 1)[0]
    if top == "vibeforcer":
        return 3, "first-party"
    if top in sys.stdlib_module_names:
        return 1, "stdlib"
    return 2, "third-party"


def _canonical_alias(name: ast.alias) -> str:
    if name.asname:
        return f"{name.name} as {name.asname}"
    return name.name


def _canonical_import_stmt(stmt: ast.Import | ast.ImportFrom) -> str:
    sec_order, section = _import_section(stmt)
    del sec_order
    if isinstance(stmt, ast.Import):
        names = sorted((_canonical_alias(a) for a in stmt.names), key=str.casefold)
        return f"{section}:import {', '.join(names)}"

    names = sorted((_canonical_alias(a) for a in stmt.names), key=str.casefold)
    dots = "." * stmt.level
    module = f"{dots}{stmt.module or ''}"
    return f"{section}:from {module} import {', '.join(names)}"


def _canonicalize_import_block(body: list[ast.stmt]) -> tuple[str | None, set[int]]:
    """Return canonical leading import block and its indices in *body*."""
    indices: set[int] = set()
    imports: list[ast.Import | ast.ImportFrom] = []
    for idx, stmt in enumerate(body):
        if not _is_import_stmt(stmt):
            break
        indices.add(idx)
        imports.append(stmt)

    if not imports:
        return None, indices

    canonical = sorted((_canonical_import_stmt(stmt) for stmt in imports), key=str.casefold)
    return "\n".join(canonical), indices


def _skip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    """Return body with the leading docstring removed, if present."""
    if not body:
        return body
    first = body[0]
    value = getattr(first, "value", None)
    literal = getattr(value, "value", None)
    is_doc = isinstance(first, ast.Expr) and isinstance(literal, str)
    return body[1:] if is_doc else body


def _has_skip_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            name = dec.id
        elif isinstance(dec, ast.Attribute):
            name = dec.attr
        else:
            name = ""
        if name in _SKIP_DECORATORS:
            return True
    return False


def _is_docstring_node(node: ast.Constant, parent_map: dict[int, ast.AST]) -> bool:
    if not isinstance(node.value, str):
        return False
    parent = parent_map.get(id(node))
    if not isinstance(parent, ast.Expr):
        return False
    gp = parent_map.get(id(parent))
    if not isinstance(
        gp, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)
    ):
        return False
    return bool(gp.body) and gp.body[0] is parent


_FUNC_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _is_clone_candidate(
    node: ast.AST,
    min_lines: int,
) -> TypeGuard[ast.FunctionDef | ast.AsyncFunctionDef]:
    """True if node is a function suitable for clone detection."""
    if not isinstance(node, _FUNC_TYPES):
        return False
    if node.name.startswith("__") and node.name.endswith("__"):
        return False
    if _has_skip_decorator(node):
        return False
    return function_body_lines(node) >= min_lines


def _end_lineno(node: ast.stmt, fallback: int) -> int:
    """Return end_lineno if available, else fallback."""
    return node.end_lineno if node.end_lineno is not None else fallback


_K = TypeVar("_K", bound=Hashable)


def _emit_group_violations(
    rule: str,
    groups: dict[_K, list[tuple[str, str, int]]],
    detail_fn: Callable[[_K, list[str]], str],
) -> list[Violation]:
    """Emit one violation per member for each group with 2+ members."""
    violations: list[Violation] = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        for rel, name, _ in members:
            others = [f"{r}:{n}" for r, n, _ in members if r != rel or n != name]
            violations.append(
                Violation(
                    rule=rule,
                    relative_path=rel,
                    identifier=name,
                    detail=detail_fn(key, others),
                )
            )
    return violations


def detect_semantic_clones(
    files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find functions with identical AST structure despite different names."""
    cfg = get_config()
    min_lines = cfg.min_function_body_lines
    parsed = ensure_parsed(files, fallback=find_source_files())

    groups: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    for pf in parsed:
        for node in ast.walk(pf.tree):
            if not _is_clone_candidate(node, min_lines):
                continue
            body = _skip_docstring(node.body)
            if not body:
                continue
            canonical = "|".join(_normalize_ast(stmt) for stmt in body)
            h = _structure_hash(canonical)
            groups[h].append((pf.rel, node.name, node.lineno))

    return _emit_group_violations(
        "semantic-clone",
        groups,
        lambda h, others: f"hash={h}, clones: {', '.join(others[:3])}",
    )
