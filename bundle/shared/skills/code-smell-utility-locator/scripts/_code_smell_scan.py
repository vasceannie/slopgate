#!/usr/bin/env python3
"""Shared AST scanning helpers for code-smell utility locator scripts."""
from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".claude",
    ".opencode",
    ".codex",
    ".hermes",
    ".snapshots",
}
SECRETISH_NAMES = {
    ".env",
    ".env.local",
    ".envrc",
    "auth.json",
    "credentials.json",
    "secrets.json",
}
PY_SUFFIXES = {".py"}
TS_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
HELPER_RE = re.compile(r"(^|_)(help|util|common|shared|normalize|parse|format|extract|resolve|load|coerce|convert)(_|$)", re.I)
BUILDER_RE = re.compile(r"(^|_)(build|builder|make|create|assemble|compose|from)(_|$)", re.I)
FACTORY_RE = re.compile(r"(^|_)(factory|create|make|new)(_|$)", re.I)
CONFIG_RE = re.compile(r"(^|_)(config|settings|options|params|preferences)(_|$)", re.I)
FACADE_RE = re.compile(r"(^|_)(facade|api|client|service|gateway|adapter)(_|$)", re.I)


@dataclass(frozen=True)
class Item:
    category: str
    path: str
    line: int
    name: str
    signature: str
    reason: str


@dataclass(frozen=True)
class FunctionRecord:
    path: str
    line: int
    name: str
    qualname: str
    signature: str
    body_hash: str
    body_size: int
    is_thin_wrapper: bool
    wrapper_target: str | None
    feature_envy_target: str | None
    feature_envy_ratio: float


def is_secretish(path: Path) -> bool:
    lowered = {part.lower() for part in path.parts}
    return bool(lowered & SECRETISH_NAMES) or any("secret" in part or "token" in part for part in lowered)


def iter_source_files(root: Path, include_tests: bool = True) -> Iterable[Path]:
    root = root.resolve()
    if root.is_file():
        if root.suffix in PY_SUFFIXES | TS_SUFFIXES and not is_secretish(root):
            yield root
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        if not include_tests and any(part in {"tests", "test", "spec"} for part in rel_parts):
            continue
        if is_secretish(path):
            continue
        if path.suffix in PY_SUFFIXES | TS_SUFFIXES:
            yield path


def relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def decorator_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = decorator_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.Call):
        return decorator_name(node.func)
    return ""


def function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str | None = None) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    name = qualname or node.name
    try:
        args = ast.unparse(node.args)
    except Exception:
        args = "..."
    ret = ""
    if node.returns is not None:
        try:
            ret = f" -> {ast.unparse(node.returns)}"
        except Exception:
            ret = " -> ..."
    return f"{prefix} {name}({args}){ret}"


def class_signature(node: ast.ClassDef, qualname: str | None = None) -> str:
    name = qualname or node.name
    bases: list[str] = []
    for base in node.bases:
        try:
            bases.append(ast.unparse(base))
        except Exception:
            bases.append("...")
    suffix = f"({', '.join(bases)})" if bases else ""
    return f"class {name}{suffix}"


def target_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = target_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return target_name(node.func)
    if isinstance(node, ast.Subscript):
        return target_name(node.value)
    return ""


def call_target(node: ast.AST) -> str | None:
    call: ast.Call | None = None
    if isinstance(node, ast.Return) and isinstance(node.value, ast.Call):
        call = node.value
    elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        call = node.value
    if call is None:
        return None
    return target_name(call.func) or None


def significant_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    return body


def normalized_body_hash(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, int]:
    body = significant_body(node)
    module = ast.Module(body=body, type_ignores=[])
    normalized = ast.dump(module, include_attributes=False)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    return digest, len(body)


def is_thin_wrapper(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, str | None]:
    if node.name.startswith("visit_"):
        return False, None
    body = significant_body(node)
    if len(body) != 1:
        return False, None
    target = call_target(body[0])
    if not target:
        return False, None
    if target in {node.name, f"self.{node.name}", f"cls.{node.name}"}:
        return False, None
    return True, target


def param_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    params = {arg.arg for arg in node.args.args + node.args.kwonlyargs}
    if node.args.vararg:
        params.add(node.args.vararg.arg)
    if node.args.kwarg:
        params.add(node.args.kwarg.arg)
    return params - {"self", "cls"}


def feature_envy(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str | None, float]:
    params = param_names(node)
    if not params:
        return None, 0.0
    counts: dict[str, int] = {}
    total = 0
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name) and child.value.id in params:
            counts[child.value.id] = counts.get(child.value.id, 0) + 1
            total += 1
    if total < 5 or not counts:
        return None, 0.0
    target, count = max(counts.items(), key=lambda item: item[1])
    ratio = count / total
    if ratio >= 0.60 and count >= 4 and target not in {"node"}:
        return target, ratio
    return None, ratio


def categories_for_name(name: str, path: Path, node_kind: str) -> list[tuple[str, str]]:
    lowered_path = "/".join(part.lower() for part in path.parts)
    out: list[tuple[str, str]] = []
    if HELPER_RE.search(name) or "util" in lowered_path or "helper" in lowered_path:
        out.append(("helpers", "helper/util naming or path"))
    if BUILDER_RE.search(name) or "builder" in lowered_path:
        out.append(("builders", "builder/make/create naming or path"))
    if FACTORY_RE.search(name) or "factory" in lowered_path:
        out.append(("factories", "factory/create/make naming or path"))
    if CONFIG_RE.search(name) or "config" in lowered_path or "settings" in lowered_path:
        out.append(("configs", "config/settings naming or path"))
    if FACADE_RE.search(name) or path.name == "__init__.py":
        out.append(("facades", "facade/api/client/service/re-export surface"))
    if node_kind == "constant" or name.isupper():
        out.append(("constants", "uppercase module-level binding"))
    return out


def scan_python(path: Path, root: Path) -> tuple[list[Item], list[FunctionRecord]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return [], []
    items: list[Item] = []
    funcs: list[FunctionRecord] = []
    rel = relpath(path, root)

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def qual(self, name: str) -> str:
            return ".".join([*self.stack, name]) if self.stack else name

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            qualname = self.qual(node.name)
            sig = class_signature(node, qualname)
            decos = {decorator_name(d) for d in node.decorator_list}
            bases = {target_name(b) for b in node.bases}
            local_categories = categories_for_name(node.name, path, "class")
            if any("dataclass" in d or d in {"define", "attrs.define", "attr.s"} for d in decos):
                local_categories.append(("dataclasses", "dataclass/attrs decorator"))
            if any(base.endswith(("BaseModel", "BaseSettings")) or base in {"TypedDict", "Protocol"} for base in bases):
                local_categories.append(("dataclasses", "schema/model-like base class"))
            if node.name.endswith(("Config", "Settings", "Options")):
                local_categories.append(("configs", "config/settings class name"))
            for category, reason in dict(local_categories).items():
                items.append(Item(category, rel, node.lineno, qualname, sig, reason))
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_function(node)

        def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            qualname = self.qual(node.name)
            sig = function_signature(node, qualname)
            for category, reason in dict(categories_for_name(node.name, path, "function")).items():
                items.append(Item(category, rel, node.lineno, qualname, sig, reason))
            body_hash, body_size = normalized_body_hash(node)
            wrapper, wrapper_target = is_thin_wrapper(node)
            envy_target, envy_ratio = feature_envy(node)
            funcs.append(FunctionRecord(rel, node.lineno, node.name, qualname, sig, body_hash, body_size, wrapper, wrapper_target, envy_target, envy_ratio))
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

    for stmt in tree.body:
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            targets: Sequence[ast.expr]
            if isinstance(stmt, ast.Assign):
                targets = stmt.targets
            else:
                targets = [stmt.target]
            for target in targets:
                name = target_name(target)
                if name and name.split(".")[-1].isupper():
                    for category, reason in dict(categories_for_name(name, path, "constant")).items():
                        items.append(Item(category, rel, getattr(stmt, "lineno", 1), name, name, reason))
        if isinstance(stmt, (ast.Import, ast.ImportFrom)) and path.name == "__init__.py":
            imported = ", ".join(alias.asname or alias.name for alias in stmt.names[:6])
            if len(stmt.names) > 6:
                imported += ", ..."
            items.append(Item("facades", rel, stmt.lineno, imported, imported, "package re-export/import surface"))
    Visitor().visit(tree)
    return items, funcs


def scan_text_like(path: Path, root: Path) -> list[Item]:
    rel = relpath(path, root)
    items: list[Item] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return items
    patterns = [
        ("constants", re.compile(r"^\s*export\s+const\s+([A-Z][A-Z0-9_]+)\b")),
        ("builders", re.compile(r"^\s*export\s+(?:async\s+)?function\s+((?:build|make|create|assemble)[A-Za-z0-9_]*)\s*\(([^)]*)\)")),
        ("factories", re.compile(r"^\s*export\s+(?:async\s+)?function\s+([A-Za-z0-9_]*(?:Factory|factory|create|make)[A-Za-z0-9_]*)\s*\(([^)]*)\)")),
        ("dataclasses", re.compile(r"^\s*export\s+(?:interface|type)\s+([A-Za-z0-9_]+)\b")),
        ("configs", re.compile(r"^\s*export\s+(?:interface|type|const|class)\s+([A-Za-z0-9_]*(?:Config|Settings|Options)[A-Za-z0-9_]*)\b")),
    ]
    for idx, line in enumerate(lines, start=1):
        for category, pattern in patterns:
            match = pattern.search(line)
            if not match:
                continue
            name = match.group(1)
            reason = "exported TypeScript/JavaScript utility-like declaration"
            items.append(Item(category, rel, idx, name, line.strip()[:160], reason))
    return items


def scan(root: Path, include_tests: bool = True) -> tuple[list[Item], list[FunctionRecord]]:
    items: list[Item] = []
    funcs: list[FunctionRecord] = []
    for path in iter_source_files(root, include_tests=include_tests):
        if path.suffix in PY_SUFFIXES:
            py_items, py_funcs = scan_python(path, root)
            items.extend(py_items)
            funcs.extend(py_funcs)
        elif path.suffix in TS_SUFFIXES:
            items.extend(scan_text_like(path, root))
    items.sort(key=lambda item: (item.category, item.path, item.line, item.name))
    funcs.sort(key=lambda item: (item.path, item.line, item.qualname))
    return items, funcs


def records_to_json(records: Iterable[object]) -> str:
    return json.dumps([asdict(record) for record in records], indent=2, sort_keys=True)
