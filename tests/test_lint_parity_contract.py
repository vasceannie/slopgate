"""Lint/hook/baseline parity contract tests."""

from __future__ import annotations

import argparse
import ast
import json
import inspect
from collections.abc import Mapping
from pathlib import Path

import pytest

from vibeforcer.cli.lint import cmd_lint
from vibeforcer.lint import _collectors
from vibeforcer.lint import _parity
from vibeforcer.lint._config import reset_config


ROOT = Path(__file__).resolve().parents[1]


def _collector_names(function_names: set[str]) -> set[str]:
    source_path = Path(inspect.getsourcefile(_collectors) or "")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in function_names:
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Tuple)
                    and child.elts
                    and isinstance(child.elts[0], ast.Constant)
                    and isinstance(child.elts[0].value, str)
                ):
                    names.add(child.elts[0].value)
    return names


def _runtime_rule_ids() -> set[str]:
    ids: set[str] = set()
    for path in (ROOT / "src" / "vibeforcer" / "rules").rglob("*.py"):
        if "_staging" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            target_name: str | None = None
            value: ast.expr | None = None
            if isinstance(node, ast.Assign):
                value = node.value
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        target_name = target.id
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                target_name = node.target.id
                value = node.value
            if (
                target_name == "rule_id"
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                ids.add(value.value)

    defaults = json.loads(
        (ROOT / "src" / "vibeforcer" / "resources" / "defaults.json").read_text(
            encoding="utf-8"
        )
    )
    for rule in defaults.get("regex_rules", []):
        if isinstance(rule, dict) and isinstance(rule.get("rule_id"), str):
            ids.add(rule["rule_id"])
    return ids


def _assert_unique_category_membership(categories: Mapping[str, frozenset[str]]) -> None:
    seen: dict[str, str] = {}
    duplicates: dict[str, tuple[str, str]] = {}
    for category, names in categories.items():
        for name in names:
            if name in seen:
                duplicates[name] = (seen[name], category)
            seen[name] = category
    assert duplicates == {}


def test_lint_collectors_are_baselined_or_classified() -> None:
    lint_check_collectors = _collector_names(
        {"_structure_src_collectors", "_ast_src_collectors", "_test_collectors", "run_all_collectors"}
    )
    test_integrity_collectors = _collector_names({"run_test_integrity_collectors"})
    current_collectors = lint_check_collectors | test_integrity_collectors
    baseline = json.loads((ROOT / "baselines.json").read_text(encoding="utf-8"))
    baseline_keys = set(baseline.get("rules", {}))

    assert current_collectors - baseline_keys - _parity.classified_collector_keys() == set()
    assert lint_check_collectors <= _parity.COLLECTOR_CATEGORIES["baseline_lint"]
    assert test_integrity_collectors <= _parity.COLLECTOR_CATEGORIES["focused_lint"]


def test_runtime_hook_rules_are_classified() -> None:
    runtime_rule_ids = _runtime_rule_ids() - {""}

    assert runtime_rule_ids - _parity.classified_hook_rule_ids() == set()
    _assert_unique_category_membership(
        {str(category): names for category, names in _parity.HOOK_RULE_CATEGORIES.items()}
    )


def test_hook_baseline_counterparts_reference_known_collectors() -> None:
    classified_collectors = _parity.classified_collector_keys()
    unknown = {
        rule_id: tuple(name for name in names if name not in classified_collectors)
        for rule_id, names in _parity.HOOK_RULE_BASELINE_COUNTERPARTS.items()
    }

    assert {rule_id: names for rule_id, names in unknown.items() if names} == {}


def test_lint_check_reports_python_parse_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "quality_gate.toml").write_text(
        "[quality_gate]\nenabled = true\n",
        encoding="utf-8",
    )
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "broken.py").write_text("def broken(:\n    return 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()

    monkeypatch.chdir(tmp_path)
    reset_config()
    try:
        result = cmd_lint(argparse.Namespace(lint_command="check", details=True))
    finally:
        reset_config()

    captured = capsys.readouterr()
    assert result == 1
    assert "[NEW] python-parse-error" in captured.out
    assert "src/pkg/broken.py:line-1" in captured.out
    assert "invalid syntax" in captured.out
