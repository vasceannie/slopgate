from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from tests.test_enrichment_public_api import context_for_source
from slopgate.context import HookContext
from slopgate.rules.python_ast._rules import (
    PythonAstHealthRule,
    PythonBroadExceptLoggerRule,
    PythonCyclomaticComplexityRule,
    PythonDeadCodeRule,
    PythonDeepNestingRule,
    PythonFeatureEnvyRule,
    PythonFlatFileSiblingsRule,
    PythonGodClassRule,
    PythonImportAliasRule,
    PythonImportFanoutRule,
    PythonLongLineRule,
    PythonLongMethodRule,
    PythonLongParameterRule,
    PythonModuleSizeRule,
    PythonPrivateImportChainRule,
    PythonSilentExceptRule,
    PythonThinWrapperRule,
)


def context_with_limits(
    tmp_path: Path,
    source: str,
    path: str = "sample.py",
    **overrides: object,
) -> HookContext:
    ctx = context_for_source(tmp_path, source, path=path)
    ctx.payload.payload["hook_event_name"] = "PreToolUse"
    ctx.payload.payload["tool_name"] = "Edit"
    return replace(ctx, config=replace(ctx.config, **overrides))


def test_broad_and_silent_exception_rules_report_distinct_findings(
    tmp_path: Path,
) -> None:
    source = """
def logged_boundary(logger) -> None:
    try:
        run()
    except Exception as exc:
        logger.error("failed: %s", exc)

def silent_boundary() -> None:
    try:
        run()
    except Exception:
        pass
""".lstrip()
    ctx = context_with_limits(tmp_path, source)

    findings = [
        *PythonBroadExceptLoggerRule().evaluate(ctx),
        *PythonSilentExceptRule().evaluate(ctx),
    ]

    assert [(item.rule_id, item.metadata.get("path")) for item in findings] == [
        ("PY-EXC-001", "sample.py"),
        ("PY-EXC-002", "sample.py"),
    ]


def test_complexity_and_dead_code_rules_report_target_functions(
    tmp_path: Path,
) -> None:
    source = """
def complicated(value: int) -> int:
    if value > 10:
        return 10
    if value > 5:
        return 5
    return value

def unreachable() -> int:
    return 1
    value = 2
""".lstrip()
    ctx = context_with_limits(tmp_path, source, python_max_complexity=2)

    findings = [
        *PythonCyclomaticComplexityRule().evaluate(ctx),
        *PythonDeadCodeRule().evaluate(ctx),
    ]

    assert [(item.rule_id, item.metadata.get("function")) for item in findings] == [
        ("PY-CODE-015", "complicated"),
        ("PY-CODE-016", "unreachable"),
    ]


def test_long_method_rule_reports_function_span(tmp_path: Path) -> None:
    source = """
def too_long() -> None:
    step_one = 1
    step_two = 2
    step_three = 3
    print(step_one, step_two, step_three)
""".lstrip()
    ctx = context_with_limits(tmp_path, source, python_long_method_lines=3)

    findings = PythonLongMethodRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("function")) for item in findings] == [
        ("PY-CODE-008", "too_long")
    ]


def test_long_parameter_rule_reports_function_signature(tmp_path: Path) -> None:
    source = """
def too_many(a: int, b: int, c: int) -> int:
    return a + b + c
""".lstrip()
    ctx = context_with_limits(tmp_path, source, python_long_parameter_limit=2)

    findings = PythonLongParameterRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("function")) for item in findings] == [
        ("PY-CODE-009", "too_many")
    ]


def test_deep_nesting_rule_reports_nested_function(tmp_path: Path) -> None:
    source = """
def nested(flag: bool) -> None:
    if flag:
        if flag:
            print(flag)
""".lstrip()
    ctx = context_with_limits(tmp_path, source, python_max_nesting_depth=1)

    findings = PythonDeepNestingRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("function")) for item in findings] == [
        ("PY-CODE-011", "nested")
    ]


def test_long_line_rule_reports_executable_line(tmp_path: Path) -> None:
    long_line = "value = " + " + ".join(f"part_{index}" for index in range(12))
    source = f"""
def long_expression() -> None:
    {long_line}
""".lstrip()
    ctx = context_with_limits(tmp_path, source, python_max_line_length=40)

    findings = PythonLongLineRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("function")) for item in findings] == [
        ("PY-CODE-010", None),
    ]


def test_feature_envy_rule_reports_external_object_bias(tmp_path: Path) -> None:
    source = """
def extract_profile() -> tuple[str, str, str, str, str, str]:
    return (
        account.name,
        account.email,
        account.region,
        account.status,
        account.plan,
        account.owner,
    )
""".lstrip()
    ctx = context_with_limits(tmp_path, source, python_feature_envy_min_accesses=3)

    findings = PythonFeatureEnvyRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("envied_object")) for item in findings] == [
        ("PY-CODE-012", "account")
    ]


def test_wrapper_and_god_class_rules_report_structural_smells(tmp_path: Path) -> None:
    source = """
def wrapper(value: str) -> str:
    return wrapped(value)

class LargeService:
    def one(self): pass
    def two(self): pass
    def three(self): pass
""".lstrip()
    ctx = context_with_limits(tmp_path, source, python_max_god_class_methods=2)

    findings = [
        *PythonThinWrapperRule().evaluate(ctx),
        *PythonGodClassRule().evaluate(ctx),
    ]

    assert [(item.rule_id, item.metadata.get("function")) for item in findings] == [
        ("PY-CODE-013", "wrapper"),
        ("PY-CODE-014", None),
    ]


def test_import_alias_rule_reports_non_standard_alias(tmp_path: Path) -> None:
    ctx = context_with_limits(tmp_path, "import hypothesis.strategies as st\n")

    findings = PythonImportAliasRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("alias")) for item in findings] == [
        ("PY-IMPORT-002", "st")
    ]


def test_import_fanout_rule_reports_excess_from_imports(tmp_path: Path) -> None:
    source = """
from service import item_alpha, item_beta, item_gamma
""".lstrip()
    ctx = context_with_limits(tmp_path, source, python_import_fanout_limit=2)

    findings = PythonImportFanoutRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("module")) for item in findings] == [
        ("PY-IMPORT-001", "service")
    ]


def test_private_import_chain_rule_reports_stacked_private_import(
    tmp_path: Path,
) -> None:
    source = """
import hypothesis.strategies as st
from slopgate.rules.python_ast._rules._private_imports import PrivateRule
from service import item_alpha, item_beta, item_gamma
""".lstrip()
    ctx = context_with_limits(tmp_path, source)

    findings = PythonPrivateImportChainRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("target")) for item in findings] == [
        ("PY-IMPORT-003", "slopgate.rules.python_ast._rules._private_imports")
    ]


def test_ast_health_rule_reports_invalid_python_content(tmp_path: Path) -> None:
    source_path = tmp_path / "broken.py"
    source_path.write_text("def broken(:\n    pass\n", encoding="utf-8")
    ctx = context_with_limits(tmp_path, "", path=str(source_path))
    ctx.payload.payload["hook_event_name"] = "PostToolUse"

    findings = PythonAstHealthRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("kind")) for item in findings] == [
        ("PY-AST-001", "parse_error")
    ]


def test_flat_sibling_rule_reports_projected_package_sprawl(tmp_path: Path) -> None:
    (tmp_path / "profile_alpha.py").write_text("ALPHA = 1\n", encoding="utf-8")
    (tmp_path / "profile_beta.py").write_text("BETA = 1\n", encoding="utf-8")
    ctx = context_with_limits(tmp_path, "GAMMA = 1\n", path=str(tmp_path / "profile_gamma.py"))

    findings = PythonFlatFileSiblingsRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("prefix")) for item in findings] == [
        ("PY-CODE-017", "profile")
    ]


def test_module_size_rule_reports_oversized_content(tmp_path: Path) -> None:
    source = "\n".join(f"value_{index} = {index}" for index in range(550))
    ctx = context_with_limits(tmp_path, source, path="large_module.py")

    findings = PythonModuleSizeRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("collector")) for item in findings] == [
        ("PY-CODE-018", "oversized-module-soft")
    ]
