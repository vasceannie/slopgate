"""Helpers for harness schema context contract tests."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any


def module_name_for_source_path(source_path: str) -> str:
    assert source_path.startswith("src/") and source_path.endswith(".py"), source_path
    return source_path.removeprefix("src/").removesuffix(".py").replace("/", ".")


def ast_sequence_values(source_path: Path, module: Any, symbol: str) -> list[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == symbol for target in node.targets):
            continue
        assert isinstance(node.value, (ast.Tuple, ast.List)), symbol
        values: list[str] = []
        for item in node.value.elts:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                values.append(item.value)
            elif isinstance(item, ast.Name) and isinstance(getattr(module, item.id, None), str):
                values.append(getattr(module, item.id))
            else:  # pragma: no cover - assertion message carries unexpected AST shape
                raise AssertionError(
                    f"{symbol} contains non-extractable AST node: {ast.dump(item)}"
                )
        return values
    raise AssertionError(f"{symbol} not found in {source_path}")


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for nested in value.values() for item in strings(nested)]
    if isinstance(value, list):
        return [item for nested in value for item in strings(nested)]
    return []


def assert_official_source(
    source_id: str, source: dict[str, Any], harness: str, kind: str
) -> None:
    assert source["harness"] == harness
    assert source["kind"] == kind
    assert source["status_code"] == 200
    assert source["content_type"]
    assert "text/html" not in source["content_type"].lower(), source_id
    assert source["url"].startswith((
        "https://docs.anthropic.com/",
        "https://opencode.ai/",
        "https://developers.openai.com/",
    )), source_id
    assert len(source["sha256"]) == 64, source_id
    assert source["bytes"] > 1000, source_id
    assert source["retrieved_at_utc"].endswith("+00:00"), source_id


def assert_installed_sources_are_extractable(
    repo_root: Path, installed_sources: list[dict[str, Any]]
) -> None:
    extracted_values_by_path = {}
    for source in installed_sources:
        source_path = repo_root / source["path"]
        assert source_path.is_file(), source
        module = importlib.import_module(module_name_for_source_path(source["path"]))
        imported = getattr(module, source["symbol"])
        assert source["load_method"] == "ast-literal"
        extracted_values_by_path[source["path"]] = ast_sequence_values(
            source_path, module, source["symbol"]
        )
        assert extracted_values_by_path[source["path"]] == list(imported)
