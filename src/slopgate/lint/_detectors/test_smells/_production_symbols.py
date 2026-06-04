"""Detectors for test-specific smells."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from slopgate.lint._helpers import (
    ParsedFile,
    ensure_parsed,
    find_test_files,
)

from ._assertion_core import _INTEGRATION_NAME_TOKENS as _INTEGRATION_NAME_TOKENS, _call_tail as _call_tail, _dotted_name as _dotted_name, _expr_preview as _expr_preview, _iter_tests as _iter_tests


_HYPOTHESIS_NAME_TOKENS = (
    "bound",
    "coerce",
    "dedupe",
    "extract",
    "filter",
    "format",
    "merge",
    "normalize",
    "parse",
    "rank",
    "score",
    "serialize",
    "sort",
    "validate",
)
_DEPRECATED_TOKENS = ("deprecated", "deprecationwarning", "legacy", "obsolete")
_INTEGRATION_HELPER_NAME_PREFIXES = ("as_", "get_", "is_", "to_")
_INTEGRATION_UTILITY_NAME_TOKENS = {
    "color",
    "colors",
    "icon",
    "icons",
    "label",
    "labels",
    "markup",
    "style",
    "styles",
    "title",
}
_INTEGRATION_UTILITY_MODULE_TOKENS = {
    ".colors",
    ".constants",
    ".icons",
    ".labels",
    ".markup",
    ".styles",
    ".theme",
    ".themes",
    ".types",
    ".typing",
    ".utils",
}
_INTEGRATION_SEAM_TOKENS = {
    "adapter",
    "api",
    "client",
    "command",
    "controller",
    "deserialize",
    "enrich",
    "error",
    "event",
    "graph",
    "handler",
    "orchestrat",
    "parse",
    "persist",
    "pipeline",
    "planner",
    "projection",
    "render",
    "repository",
    "route",
    "router",
    "screen",
    "seam",
    "serialize",
    "service",
    "sse",
    "store",
    "stream",
    "sync",
    "workflow",
}
_COVERAGE_JSON_NAMES = ("coverage.json", ".coverage.json")
_COVERAGE_XML_NAMES = ("coverage.xml", ".coverage.xml")
_REPLACEMENT_PATTERNS = (
    re.compile(r"use\s+([A-Za-z_][\w.]+)\s+instead", re.IGNORECASE),
    re.compile(r"replaced\s+by\s+([A-Za-z_][\w.]+)", re.IGNORECASE),
    re.compile(r"migrate\s+to\s+([A-Za-z_][\w.]+)", re.IGNORECASE),
)


@dataclass(frozen=True)
class _ProductionSymbol:
    name: str
    qualname: str
    module: str
    relative_path: str
    lineno: int
    kind: str
    parameter_count: int
    branch_score: int
    transform_score: int
    deprecated: bool
    replacement: str | None


def _module_name_from_rel(rel: str) -> str:
    path = rel[:-3] if rel.endswith(".py") else rel
    parts = path.split("/")
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(part for part in parts if part)


def _public_top_level_defs(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef]:
    defs: list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if node.name.startswith("_"):
            continue
        defs.append(node)
    return defs


def _decorator_texts(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> list[str]:
    return [_expr_preview(decorator).lower() for decorator in node.decorator_list]


def _docstring_text(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str:
    docstring = ast.get_docstring(node)
    return docstring.lower() if docstring else ""


def _replacement_hint(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str | None:
    docstring = ast.get_docstring(node) or ""
    for pattern in _REPLACEMENT_PATTERNS:
        match = pattern.search(docstring)
        if match is not None:
            return match.group(1)
    return None


def _node_mentions_deprecated(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> bool:
    text = " ".join([_docstring_text(node), *_decorator_texts(node)])
    if any(token in text for token in _DEPRECATED_TOKENS):
        return True
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and _call_tail(child) == "warn":
            preview = _expr_preview(child).lower()
            if "deprecationwarning" in preview or "deprecated" in preview:
                return True
    return False


def _parameter_count(node: ast.AST) -> int:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return 0
    args = node.args
    params = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    return len([param for param in params if param.arg not in {"self", "cls"}])


def _branch_score(node: ast.AST) -> int:
    branch_nodes = (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.BoolOp, ast.Compare, ast.Match)
    return sum(1 for child in ast.walk(node) if isinstance(child, branch_nodes))


def _transform_score(node: ast.AST) -> int:
    score = 0
    transform_nodes = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.Subscript)
    for child in ast.walk(node):
        if isinstance(child, transform_nodes):
            score += 1
        if isinstance(child, ast.Call):
            tail = _call_tail(child).lower()
            if tail in {"append", "extend", "update", "get", "split", "join", "strip", "replace", "lower", "upper", "sort", "sorted"}:
                score += 1
    return score


def _production_symbols(parsed_src: list[ParsedFile]) -> list[_ProductionSymbol]:
    symbols: list[_ProductionSymbol] = []
    for pf in parsed_src:
        module = _module_name_from_rel(pf.rel)
        if not module:
            continue
        for node in _public_top_level_defs(pf.tree):
            qualname = f"{module}.{node.name}"
            symbols.append(
                _ProductionSymbol(
                    name=node.name,
                    qualname=qualname,
                    module=module,
                    relative_path=pf.rel,
                    lineno=node.lineno,
                    kind="class" if isinstance(node, ast.ClassDef) else "function",
                    parameter_count=_parameter_count(node),
                    branch_score=_branch_score(node),
                    transform_score=_transform_score(node),
                    deprecated=_node_mentions_deprecated(node),
                    replacement=_replacement_hint(node),
                )
            )
    return symbols


def _module_names(parsed_src: list[ParsedFile]) -> set[str]:
    return {name for pf in parsed_src for name in [_module_name_from_rel(pf.rel)] if name}


def _package_roots(modules: set[str]) -> set[str]:
    return {module.split(".", maxsplit=1)[0] for module in modules if module}


def _add_import_from_reference_tokens(tokens: set[str], node: ast.ImportFrom) -> None:
    if node.module:
        tokens.add(node.module.lower())
    for alias in node.names:
        tokens.add(alias.name.lower())
        if node.module:
            tokens.add(f"{node.module}.{alias.name}".lower())


def _add_import_reference_tokens(tokens: set[str], node: ast.Import) -> None:
    for alias in node.names:
        tokens.add(alias.name.lower())


def _reference_tokens_for_node(node: ast.AST) -> set[str]:
    tokens: set[str] = set()
    if isinstance(node, ast.Name):
        tokens.add(node.id.lower())
    elif isinstance(node, ast.Attribute):
        tokens.add(node.attr.lower())
        dotted = _dotted_name(node).lower()
        if dotted:
            tokens.add(dotted)
    elif isinstance(node, ast.ImportFrom):
        _add_import_from_reference_tokens(tokens, node)
    elif isinstance(node, ast.Import):
        _add_import_reference_tokens(tokens, node)
    return tokens


def _reference_tokens_for_tree(tree: ast.AST) -> set[str]:
    tokens: set[str] = set()
    for child in ast.walk(tree):
        tokens.update(_reference_tokens_for_node(child))
    return tokens


def _test_reference_tokens(parsed_tests: list[ParsedFile]) -> set[str]:
    tokens: set[str] = set()
    for pf in parsed_tests:
        tokens.update(_reference_tokens_for_tree(pf.tree))
    return tokens


def _production_test_inputs(
    src_files: list[Path] | list[ParsedFile] | None,
    test_files: list[Path] | list[ParsedFile] | None,
) -> tuple[list[ParsedFile], list[ParsedFile], set[str]]:
    parsed_src = ensure_parsed(src_files, fallback=[])
    parsed_tests = ensure_parsed(test_files, fallback=find_test_files())
    return parsed_src, parsed_tests, _test_reference_tokens(parsed_tests)


def _integration_test_reference_tokens(parsed_tests: list[ParsedFile]) -> set[str]:
    tokens: set[str] = set()
    for pf in parsed_tests:
        path_claims = any(token in pf.rel.lower() for token in _INTEGRATION_NAME_TOKENS)
        for test_node in _iter_tests(pf.tree):
            name_claims = any(token in test_node.name.lower() for token in _INTEGRATION_NAME_TOKENS)
            if path_claims or name_claims:
                tokens.update(_reference_tokens_for_tree(test_node))
    return tokens


def _symbol_is_referenced(symbol: _ProductionSymbol, tokens: set[str]) -> bool:
    return symbol.name.lower() in tokens or symbol.qualname.lower() in tokens
