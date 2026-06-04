"""Regression coverage for import-stable package splits of large core modules."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from slopgate.lint._detectors.code_smells import detect_oversized_modules

SPLIT_MODULES = (
    "src/slopgate/lint/_detectors/test_smells.py",
    "src/slopgate/lint/_detectors/duplicates.py",
    "src/slopgate/rules/common.py",
    "src/slopgate/rules/python_ast/_rules.py",
    "src/slopgate/rules/stop_rules.py",
    "src/slopgate/state.py",
    "src/slopgate/config.py",
    "src/slopgate/engine.py",
    "src/slopgate/util/payloads.py",
    "src/slopgate/stats.py",
)

SOFT_OVERSIZED_SPLIT_TARGETS = (
    "src/slopgate/installer/_suite.py",
    "src/slopgate/rules/python_ast/_rules/_module_size_projection.py",
)

PUBLIC_IMPORT_CASES = (
    ("slopgate.lint._detectors.test_smells", "detect_long_tests"),
    ("slopgate.lint._detectors.test_smells", "detect_mock_theater"),
    ("slopgate.lint._detectors.test_smells", "detect_untested_production_code"),
    ("slopgate.lint._detectors.test_smells", "detect_stale_test_references"),
    ("slopgate.lint._detectors.duplicates", "detect_semantic_clones"),
    ("slopgate.lint._detectors.duplicates", "detect_repeated_literals"),
    ("slopgate.lint._detectors.duplicates", "detect_repeated_blocks"),
    ("slopgate.lint._detectors.duplicates", "detect_duplicate_call_sequences"),
    ("slopgate.rules.common", "PromptContextRule"),
    ("slopgate.rules.common", "SensitiveDataRule"),
    ("slopgate.rules.common", "PostEditLintRule"),
    ("slopgate.rules.common", "is_safe_read_shell_command"),
    ("slopgate.rules.python_ast._rules", "PythonModuleSizeRule"),
    ("slopgate.rules.python_ast._rules", "PythonAstHealthRule"),
    ("slopgate.rules.python_ast._rules", "PythonFlatFileSiblingsRule"),
    ("slopgate.rules.python_ast._rules", "PythonImportFanoutRule"),
    ("slopgate.rules.stop_rules", "RequireQualityCheckRule"),
    ("slopgate.rules.stop_rules", "RulebookSecurityRule"),
    ("slopgate.rules.stop_rules", "RepoEnrollmentProtectionRule"),
    ("slopgate.state", "HookStateStore"),
    ("slopgate.state", "RetryLockPayload"),
    ("slopgate.config", "load_config"),
    ("slopgate.config", "enroll_repo"),
    ("slopgate.engine", "evaluate_payload"),
    ("slopgate.engine", "render_output"),
    ("slopgate.util.payloads", "HookPayload"),
    ("slopgate.util.payloads", "shell_command_paths"),
    ("slopgate.stats", "analyze"),
    ("slopgate.stats", "run_stats"),
)


@pytest.mark.parametrize("legacy_module", SPLIT_MODULES)
def test_large_core_module_is_package_with_no_legacy_module_file(legacy_module: str) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / legacy_module
    package_path = module_path.with_suffix("")

    assert not module_path.exists(), f"legacy oversized module remains: {legacy_module}"
    assert (package_path / "__init__.py").is_file(), f"missing package facade: {package_path}"


@pytest.mark.parametrize("module_name", [*SOFT_OVERSIZED_SPLIT_TARGETS])
def test_split_target_is_not_soft_oversized(module_name: str) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / module_name

    violations = detect_oversized_modules([module_path])

    assert violations == []


@pytest.mark.parametrize(("module_name", "public_name"), PUBLIC_IMPORT_CASES)
def test_split_module_public_import_remains_available(module_name: str, public_name: str) -> None:
    module = import_module(module_name)

    assert getattr(module, public_name).__name__ == public_name
