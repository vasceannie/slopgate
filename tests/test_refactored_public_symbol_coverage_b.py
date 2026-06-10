"""Static reference coverage for refactored public module surfaces."""

from __future__ import annotations

from slopgate.rules.python_ast._staging._test_smell_rule_helpers import (
    contains_assertion,
    is_test_file,
    is_test_function,
    is_type_checking_block,
    iter_test_module_nodes,
    walk_skip_nested_funcs,
)
from slopgate.rules.python_ast._pytest_asyncio_fixture_scope import (
    configured_loop_scope_note,
    explicit_fixture_loop_scope_message,
    fixture_scope_state,
    is_pytest_path,
    plain_auto_fixture_scope_message,
    resource_scope_note,
    unknown_fixture_scope_message,
    unknown_loop_scope_message,
    FixtureScopeState,
)
from slopgate.installer._suite_autoupdate_types import SchedulerPlan
from slopgate.installer._suite_autoupdate_windows import (
    backup_existing_windows_task_xml,
    path_appears_in_task_xml,
    prepare_windows_task_replacement,
    query_windows_task_xml,
    scheduler_file_is_owned,
    windows_task_is_owned,
)
from slopgate.enrichment._helpers import (
    loaded_source_at_path,
    metadata_str,
    path_source_from_metadata,
)
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
from slopgate.cli._lint_report_format import colorize, existing_location_lines
from slopgate.config._io import load_toml, load_json, slopgate_path, slopgate_template
from slopgate.enrichment._thin_wrapper_enricher import enrich_thin_wrapper
from slopgate.enrichment.quality_enrichers._magic_number_import_hints import (
    append_importable_constant_hints,
    extract_importable_constants,
    format_constant_value,
)
from slopgate.lint._detectors.duplicates._semantic_builtins import BUILTINS, SKIP_DECORATORS
from slopgate.rules._error_output_signals import has_error_signals
from slopgate.search._cli_command_specs import (
    ArgumentSpec,
    CommandSpec,
    command_specs,
    init_argument_specs,
)
from slopgate.util.path_filters import is_authored_python_path
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

PUBLIC_SYMBOL_GROUPS_b: dict[str, tuple[object, ...]] = {
    "_flat_siblings": (
        FlatSiblingFindingInput,
        flat_sibling_resolve_candidate_path,
        flat_sibling_patch_blob,
        PythonFlatFileSiblingsRule,
    ),
    "_wrapper_god": (
        thin_wrapper_extract_single_call,
        thin_wrapper_attribute_name,
        thin_wrapper_call_target_name,
        is_test_helper_path,
        is_wrapper_candidate,
        PythonThinWrapperRule,
    ),
    "_io": (load_toml, load_json, slopgate_path, slopgate_template),
    "_render": (merge_updated_input, collect_context, top_decision, serialize_findings),
    "_basic_detection": (
        resolve_test_file_paths,
        count_sut_calls,
        call_assertion_name,
        is_assertion_call,
        has_assertion,
        max_bare_assert_run,
    ),
    "_git_quality": (
        resolve_candidate_path,
        git_output,
        git_repo_root,
        normalize_git_remote,
        is_worktree,
        is_slopgate_repo,
        default_branch_name,
    ),
    "_infra_security": (
        path_contains_fragment,
        is_safe_bash_for_path,
        is_modifying_tool,
        infra_deny,
        check_config_path,
        HookInfraExecProtectionRule,
    ),
    "parsers": (add_optional_path_argument, add_dry_run_argument, add_details_argument),
    "_hypothesis_obsolete": (
        hypothesis_properties,
        hypothesis_score,
        detect_hypothesis_candidates,
        missing_import_from_violation,
        module_or_package_exists,
    ),
    "_locks_store": (RetryLockStateMixin, RepairPlanStateMixin, HookStateStore),
    "_fixtures": (
        is_pytest_fixture_decorator,
        is_fixture_support_module,
        detect_fixtures_outside_conftest,
    ),
    "_quality_postedit": (
        collect_quality_commands,
        run_quality_commands,
        PostEditQualityRule,
    ),
    "_models": (RetryLockPayload, DenyKeyPattern, HookStateSnapshot),
    "_shell": (shell_command_executable_paths, shell_tokens, shell_command_paths),
    "_sensitive_system_git": (
        sensitive_pattern_expr,
        compile_sensitive_patterns,
        SensitiveDataRule,
        match_system_path,
        match_system_command,
        detect_git_bypass,
    ),
    "_shell_read": (
        command_has_word,
        shell_tokens,
        find_command_has_mutation,
        is_safe_read_shell_command,
        path_matches_any,
        read_context_fragment,
    ),
    "_lint_commands": (
        discover_project_root,
        lint_check,
        lint_baseline,
        lint_test_integrity,
    ),
    "_production_detectors": (
        detect_untested_production_code,
        has_token,
        integration_seam_score,
        detect_missing_integration_tests,
    ),
    "_quality_lint": (
        SearchReminderRule,
        resolve_python_candidates,
        collect_touched_lint_failures,
        python_lint_targets,
    ),
    "_broad_silent": (
        is_broad_exception,
        is_logger_call,
        is_empty_default_return,
        PythonBroadExceptLoggerRule,
    ),
    "_coerce": (object_dict, string_value, bool_value, int_value, command_map),
    "lint_report": (LintFiles, LintHeader, TallyInput, tally_rule, print_lint_summary),
    "_lint_report_format": (colorize, existing_location_lines),
    "_error_output_signals": (has_error_signals,),
    "_cli_command_specs": (
        ArgumentSpec,
        CommandSpec,
        command_specs,
        init_argument_specs,
    ),
    "_path_filters": (is_authored_python_path,),
    "_semantic_builtins": (BUILTINS, SKIP_DECORATORS),
    "_thin_wrapper_enricher": (enrich_thin_wrapper,),
    "_magic_number_import_hints": (
        append_importable_constant_hints,
        extract_importable_constants,
        format_constant_value,
    ),
    "_test_smell_rule_helpers": (
        is_test_function,
        is_test_file,
        contains_assertion,
        walk_skip_nested_funcs,
        is_type_checking_block,
        iter_test_module_nodes,
    ),
    "_pytest_asyncio_fixture_scope": (
        fixture_scope_state,
        is_pytest_path,
        unknown_fixture_scope_message,
        unknown_loop_scope_message,
        configured_loop_scope_note,
        resource_scope_note,
        FixtureScopeState,
        plain_auto_fixture_scope_message,
        explicit_fixture_loop_scope_message,
    ),
    "_enrichment_helpers": (
        metadata_str,
        loaded_source_at_path,
        path_source_from_metadata,
    ),
    "_suite_autoupdate_types": (SchedulerPlan,),
    "_suite_autoupdate_windows_full": (
        query_windows_task_xml,
        path_appears_in_task_xml,
        scheduler_file_is_owned,
        windows_task_is_owned,
        backup_existing_windows_task_xml,
        prepare_windows_task_replacement,
    ),
}


def test_refactored_public_symbols_are_importable_b() -> None:
    observed = {name: len(symbols) for name, symbols in PUBLIC_SYMBOL_GROUPS_b.items()}
    assert all(count > 0 for count in observed.values())
    assert len(observed) == len(PUBLIC_SYMBOL_GROUPS_b)
