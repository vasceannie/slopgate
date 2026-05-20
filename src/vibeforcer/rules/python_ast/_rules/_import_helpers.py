"""Python AST runtime rules."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, NamedTuple
if TYPE_CHECKING:
    pass


_ALLOWED_IMPORT_ALIASES: dict[str, str] = {
    "altair": "alt",
    "geopandas": "gpd",
    "jax.numpy": "jnp",
    "matplotlib": "mpl",
    "matplotlib.pyplot": "plt",
    "networkx": "nx",
    "numpy": "np",
    "pandas": "pd",
    "plotly.express": "px",
    "polars": "pl",
    "pyarrow": "pa",
    "pyspark.sql.functions": "F",
    "pyspark.sql.types": "T",
    "pyspark.sql.window": "W",
    "scipy": "sp",
    "seaborn": "sns",
    "sqlalchemy": "sa",
    "statsmodels.api": "sm",
    "statsmodels.formula.api": "smf",
    "sympy": "sp",
    "tensorflow": "tf",
    "tkinter": "tk",
    "tkinter.ttk": "ttk",
    "torch.nn": "nn",
    "xml.etree.ElementTree": "ET",
}


def _import_alias_full_name(node: ast.Import | ast.ImportFrom, name: ast.alias) -> str:
    """Return the imported object path used for alias allowlist checks."""
    if isinstance(node, ast.Import):
        return name.name
    module = node.module or ""
    if not module:
        return name.name
    return f"{module}.{name.name}"


def _allowed_import_alias(node: ast.Import | ast.ImportFrom, name: ast.alias) -> bool:
    """Return True when an import alias is a canonical library convention."""
    if name.asname is None:
        return True
    if name.name == "*":
        return False
    full_name = _import_alias_full_name(node, name)
    return _ALLOWED_IMPORT_ALIASES.get(full_name) == name.asname


def _import_alias_replacement(node: ast.Import | ast.ImportFrom, name: ast.alias) -> tuple[str, str]:
    """Return exact replacement import text and usage hint for a blocked alias."""
    if isinstance(node, ast.Import):
        return f"import {name.name}", f"{name.name}.<name>(...)"
    module = node.module or ""
    if module:
        return f"from {module} import {name.name}", f"{name.name}.<name>(...)"
    return f"import {name.name}", f"{name.name}.<name>(...)"


def _patch_added_source(source: str) -> str | None:
    """Extract added Python lines from a patch-like content target."""
    added: list[str] = []
    for line in source.splitlines():
        if line.startswith("+++") or line.startswith("***"):
            continue
        if line.startswith("+"):
            added.append(line[1:])
    if not added:
        return None
    return "\n".join(added)


def _is_private_module_segment(segment: str) -> bool:
    """Return True for a single-underscore implementation module segment."""
    return segment.startswith("_") and not segment.startswith("__")


def _private_module_segments(module_name: str) -> list[str]:
    """Return private segments from a dotted module/import path."""
    return [segment for segment in module_name.split(".") if _is_private_module_segment(segment)]


def _module_path_from_python_file(path_value: str) -> str:
    """Return a dotted module-ish path from a Python file path."""
    normalized = path_value.replace("\\", "/").strip("/")
    if not normalized.endswith((".py", ".pyi")):
        return normalized.replace("/", ".")
    module_path = normalized.rsplit(".", 1)[0].replace("/", ".")
    if module_path.endswith(".__init__"):
        return module_path.removesuffix(".__init__")
    return module_path


def _imported_modules(node: ast.AST) -> list[tuple[int, str]]:
    """Return imported module paths from an import node."""
    if isinstance(node, ast.ImportFrom) and node.module:
        return [(node.lineno, node.module)]
    if isinstance(node, ast.Import):
        return [(node.lineno, alias.name) for alias in node.names]
    return []


class _PrivateImportFinding(NamedTuple):
    path_value: str
    target: str
    kind: str
    line: int | None = None
