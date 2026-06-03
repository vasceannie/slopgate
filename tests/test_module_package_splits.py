"""Regression coverage for import-stable package splits of large core modules."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from vibeforcer.lint._detectors.code_smells import detect_oversized_modules

SPLIT_MODULES = (
    "src/vibeforcer/lint/_detectors/test_smells.py",
    "src/vibeforcer/lint/_detectors/duplicates.py",
    "src/vibeforcer/rules/common.py",
    "src/vibeforcer/rules/python_ast/_rules.py",
    "src/vibeforcer/rules/stop_rules.py",
    "src/vibeforcer/state.py",
    "src/vibeforcer/config.py",
    "src/vibeforcer/engine.py",
    "src/vibeforcer/util/payloads.py",
    "src/vibeforcer/stats.py",
)

SOFT_OVERSIZED_SPLIT_TARGETS = (
    "src/vibeforcer/installer/_suite.py",
    "src/vibeforcer/rules/python_ast/_rules/_module_size_projection.py",
)

PUBLIC_IMPORT_CASES = (
    ("vibeforcer.lint._detectors.test_smells", "detect_long_tests"),
    ("vibeforcer.lint._detectors.test_smells", "detect_mock_theater"),
    ("vibeforcer.lint._detectors.test_smells", "detect_untested_production_code"),
    ("vibeforcer.lint._detectors.test_smells", "detect_obsolete_or_deprecated_tests"),
    ("vibeforcer.lint._detectors.duplicates", "detect_semantic_clones"),
    ("vibeforcer.lint._detectors.duplicates", "detect_repeated_literals"),
    ("vibeforcer.lint._detectors.duplicates", "detect_repeated_blocks"),
    ("vibeforcer.lint._detectors.duplicates", "detect_duplicate_call_sequences"),
    ("vibeforcer.rules.common", "PromptContextRule"),
    ("vibeforcer.rules.common", "SensitiveDataRule"),
    ("vibeforcer.rules.common", "PostEditLintRule"),
    ("vibeforcer.rules.common", "is_safe_read_shell_command"),
    ("vibeforcer.rules.python_ast._rules", "PythonModuleSizeRule"),
    ("vibeforcer.rules.python_ast._rules", "PythonAstHealthRule"),
    ("vibeforcer.rules.python_ast._rules", "PythonFlatFileSiblingsRule"),
    ("vibeforcer.rules.python_ast._rules", "PythonImportFanoutRule"),
    ("vibeforcer.rules.stop_rules", "RequireQualityCheckRule"),
    ("vibeforcer.rules.stop_rules", "RulebookSecurityRule"),
    ("vibeforcer.rules.stop_rules", "RepoEnrollmentProtectionRule"),
    ("vibeforcer.state", "HookStateStore"),
    ("vibeforcer.state", "RetryLockPayload"),
    ("vibeforcer.config", "load_config"),
    ("vibeforcer.config", "enroll_repo"),
    ("vibeforcer.engine", "evaluate_payload"),
    ("vibeforcer.engine", "render_output"),
    ("vibeforcer.util.payloads", "HookPayload"),
    ("vibeforcer.util.payloads", "shell_command_paths"),
    ("vibeforcer.stats", "analyze"),
    ("vibeforcer.stats", "run_stats"),
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
