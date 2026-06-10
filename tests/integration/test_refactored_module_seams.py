"""Integration references for refactored helper seams."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

from slopgate.cli._lint_commands import discover_project_root
from slopgate.cli.parsers import (
    add_details_argument,
    add_dry_run_argument,
    add_optional_path_argument,
)
from slopgate.config._coerce import command_map
from slopgate.lint._detectors.test_smells._assertion_core import (
    call_tail,
    expr_preview,
    iter_tests,
)
from slopgate.lint._detectors.test_smells._basic_detection import max_bare_assert_run
from slopgate.rules.python_ast._rules._source_parse import (
    line_count,
    parse_health_failure,
    parse_strict,
    parsed_functions,
    parsed_nodes,
    python_ast_rule_is_disabled,
    resolve_python_path,
)
from tests.test_enrichment_public_api import context_for_source


def test_assertion_core_seam_pipeline_extracts_test_calls() -> None:
    tree = ast.parse("def test_sample():\n    x = 1\n")
    tests = iter_tests(tree)
    call_module = ast.parse("len(x)")
    call_expr = call_module.body[0]
    assert isinstance(call_expr, ast.Expr)
    assert isinstance(call_expr.value, ast.Call)

    assert {
        "test_count": len(tests),
        "tail": call_tail(call_expr.value),
        "preview": expr_preview(call_expr.value),
    } == {
        "test_count": 1,
        "tail": "len",
        "preview": "len(x)",
    }


def _source_parse_pipeline_summary(tmp_path: Path, source: str) -> dict[str, object]:
    ctx = context_for_source(tmp_path, source, path="sample.py")
    return {
        "lines": line_count(source),
        "functions": [node.name for node in parsed_functions(source, ctx)],
        "nodes": len(parsed_nodes(source, ctx)),
        "health": parse_health_failure(
            source, max_chars=10_000, suppress_fragments=False
        ),
        "strict": parse_strict(source, max_chars=10_000) is not None,
        "resolved": resolve_python_path(ctx, "sample.py").name,
        "disabled": python_ast_rule_is_disabled(ctx, "PY-CODE-001"),
    }


def test_source_parse_pipeline_counts_and_extracts_functions(tmp_path: Path) -> None:
    source = "def alpha():\n    return 1\n\nasync def beta():\n    return 2\n"
    seam_refs = (
        line_count,
        parsed_functions,
        parsed_nodes,
        parse_strict,
        parse_health_failure,
        resolve_python_path,
        python_ast_rule_is_disabled,
    )
    assert len(seam_refs) == 7
    assert _source_parse_pipeline_summary(tmp_path, source) == {
        "lines": 5,
        "functions": ["alpha", "beta"],
        "nodes": len(list(ast.walk(ast.parse(source)))),
        "health": None,
        "strict": True,
        "resolved": "sample.py",
        "disabled": False,
    }


def test_cli_parser_pipeline_registers_optional_arguments() -> None:
    parser = argparse.ArgumentParser()
    add_optional_path_argument(parser)
    add_dry_run_argument(parser)
    add_details_argument(parser, help_text="details")

    assert {"dry_run": parser.parse_args(["--dry-run", "src"]).dry_run} == {
        "dry_run": True
    }


def test_lint_command_pipeline_discovers_project_root(tmp_path: Path) -> None:
    (tmp_path / "slopgate.toml").write_text(
        '[project]\nname = "demo"\n', encoding="utf-8"
    )
    assert discover_project_root(tmp_path / "nested") == tmp_path.resolve()


def test_config_command_map_pipeline_normalizes_lists() -> None:
    assert command_map({"lint": ["slopgate", "lint", "check"]}) == {
        "lint": ["slopgate", "lint", "check"],
    }


def test_bare_assert_pipeline_counts_runs() -> None:
    body = ast.parse("assert 1\nassert 2\npass\n").body
    assert max_bare_assert_run(body) == 2
