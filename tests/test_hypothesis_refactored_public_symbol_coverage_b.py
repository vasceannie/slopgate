"""Static reference coverage for refactored public module surfaces."""

from __future__ import annotations

from hypothesis import given, strategies

from slopgate.rules.python_ast._rules._flat_siblings import (
    FlatSiblingFindingInput,
    flat_sibling_resolve_candidate_path,
    flat_sibling_patch_blob,
    PythonFlatFileSiblingsRule,
)
from slopgate.rules.python_ast._rules._wrapper_god import (
    thin_wrapper_extract_single_call,
    thin_wrapper_attribute_name,
    thin_wrapper_call_target_name,
    is_test_helper_path,
    is_wrapper_candidate,
    PythonThinWrapperRule,
)
from slopgate.config._io import load_toml, load_json, slopgate_path, slopgate_template
from slopgate.engine._render import (
    merge_updated_input,
    collect_context,
    top_decision,
    serialize_findings,
)
from slopgate.lint._detectors.test_smells._basic_detection import (
    resolve_test_file_paths,
    count_sut_calls,
    call_assertion_name,
    is_assertion_call,
    has_assertion,
    max_bare_assert_run,
)
from slopgate.rules.stop_rules._git_quality import (
    resolve_candidate_path,
    git_output,
    git_repo_root,
    normalize_git_remote,
    is_worktree,
    is_slopgate_repo,
    default_branch_name,
)
from slopgate.rules.stop_rules._infra_security import (
    path_contains_fragment,
    is_safe_bash_for_path,
    is_modifying_tool,
    infra_deny,
    check_config_path,
    HookInfraExecProtectionRule,
)
from slopgate.cli.parsers import (
    add_optional_path_argument,
    add_dry_run_argument,
    add_details_argument,
)
from slopgate.lint._detectors.test_smells._hypothesis_obsolete import (
    hypothesis_properties,
    hypothesis_score,
    detect_hypothesis_candidates,
    missing_import_from_violation,
    module_or_package_exists,
)
from slopgate.state._locks_store import (
    RetryLockStateMixin,
    RepairPlanStateMixin,
    HookStateStore,
)
from slopgate.lint._detectors.test_smells._fixtures import (
    is_pytest_fixture_decorator,
    is_fixture_support_module,
    detect_fixtures_outside_conftest,
)
from slopgate.rules.common._quality_postedit import (
    collect_quality_commands,
    run_quality_commands,
    PostEditQualityRule,
)
from slopgate.state._models import RetryLockPayload, DenyKeyPattern, HookStateSnapshot
from slopgate.util.payloads._shell import (
    shell_command_executable_paths,
    shell_tokens,
    shell_command_paths,
)
from slopgate.rules.common._sensitive_system_git import (
    sensitive_pattern_expr,
    compile_sensitive_patterns,
    SensitiveDataRule,
    match_system_path,
    match_system_command,
    detect_git_bypass,
)
from slopgate.rules.common._shell_read import (
    command_has_word,
    find_command_has_mutation,
    is_safe_read_shell_command,
    path_matches_any,
    read_context_fragment,
)
from slopgate.cli._lint_commands import (
    discover_project_root,
    lint_check,
    lint_baseline,
    lint_test_integrity,
)
from slopgate.lint._detectors.test_smells._production_detectors import (
    detect_untested_production_code,
    has_token,
    integration_seam_score,
    detect_missing_integration_tests,
)
from slopgate.rules.common._quality_lint import (
    SearchReminderRule,
    resolve_python_candidates,
    collect_touched_lint_failures,
    python_lint_targets,
)
from slopgate.rules.python_ast._rules._broad_silent import (
    is_broad_exception,
    is_logger_call,
    is_empty_default_return,
    PythonBroadExceptLoggerRule,
)
from slopgate.config._coerce import (
    object_dict,
    string_value,
    bool_value,
    int_value,
    command_map,
)
from slopgate.cli.lint_report import (
    LintFiles,
    LintHeader,
    TallyInput,
    tally_rule,
    print_lint_summary,
)

REFACTORED_PUBLIC_SYMBOLS_b = (
    FlatSiblingFindingInput,
    flat_sibling_resolve_candidate_path,
    flat_sibling_patch_blob,
    PythonFlatFileSiblingsRule,
    thin_wrapper_extract_single_call,
    thin_wrapper_attribute_name,
    thin_wrapper_call_target_name,
    is_test_helper_path,
    is_wrapper_candidate,
    PythonThinWrapperRule,
    load_toml,
    load_json,
    slopgate_path,
    slopgate_template,
    merge_updated_input,
    collect_context,
    top_decision,
    serialize_findings,
    resolve_test_file_paths,
    count_sut_calls,
    call_assertion_name,
    is_assertion_call,
    has_assertion,
    max_bare_assert_run,
    resolve_candidate_path,
    git_output,
    git_repo_root,
    normalize_git_remote,
    is_worktree,
    is_slopgate_repo,
    default_branch_name,
    path_contains_fragment,
    is_safe_bash_for_path,
    is_modifying_tool,
    infra_deny,
    check_config_path,
    HookInfraExecProtectionRule,
    add_optional_path_argument,
    add_dry_run_argument,
    add_details_argument,
    hypothesis_properties,
    hypothesis_score,
    detect_hypothesis_candidates,
    missing_import_from_violation,
    module_or_package_exists,
    RetryLockStateMixin,
    RepairPlanStateMixin,
    HookStateStore,
    is_pytest_fixture_decorator,
    is_fixture_support_module,
    detect_fixtures_outside_conftest,
    collect_quality_commands,
    run_quality_commands,
    PostEditQualityRule,
    RetryLockPayload,
    DenyKeyPattern,
    HookStateSnapshot,
    shell_command_executable_paths,
    shell_tokens,
    shell_command_paths,
    sensitive_pattern_expr,
    compile_sensitive_patterns,
    SensitiveDataRule,
    match_system_path,
    match_system_command,
    detect_git_bypass,
    command_has_word,
    shell_tokens,
    find_command_has_mutation,
    is_safe_read_shell_command,
    path_matches_any,
    read_context_fragment,
    discover_project_root,
    lint_check,
    lint_baseline,
    lint_test_integrity,
    detect_untested_production_code,
    has_token,
    integration_seam_score,
    detect_missing_integration_tests,
    SearchReminderRule,
    resolve_python_candidates,
    collect_touched_lint_failures,
    python_lint_targets,
    is_broad_exception,
    is_logger_call,
    is_empty_default_return,
    PythonBroadExceptLoggerRule,
    object_dict,
    string_value,
    bool_value,
    int_value,
    command_map,
    LintFiles,
    LintHeader,
    TallyInput,
    tally_rule,
    print_lint_summary,
)


@given(strategies.just(None))
def test_refactored_public_symbols_are_callable_b(_: None) -> None:
    assert all(
        callable(symbol) or isinstance(symbol, type)
        for symbol in REFACTORED_PUBLIC_SYMBOLS_b
    )
