"""Static reference coverage for refactored public module surfaces."""

from __future__ import annotations

import importlib

from hypothesis import given, strategies

_python_ast_rules = importlib.import_module("slopgate.rules.python_ast._rules")
_config_io = importlib.import_module("slopgate.config._io")
_engine_render = importlib.import_module("slopgate.engine._render")
_test_smells = importlib.import_module("slopgate.lint._detectors.test_smells")
_git_quality = importlib.import_module("slopgate.rules.stop_rules._git_quality")
_infra_security = importlib.import_module("slopgate.rules.stop_rules._infra_security")
_cli_parsers = importlib.import_module("slopgate.cli.parsers")
_locks_store = importlib.import_module("slopgate.state._locks_store")
_postedit_quality = importlib.import_module("slopgate.rules.common.quality.postedit")
_state_models = importlib.import_module("slopgate.state._models")
_payload_shell = importlib.import_module("slopgate.util.payloads._shell")
_sensitive_system_git = importlib.import_module(
    "slopgate.rules.common._sensitive_system_git"
)
_rules_common = importlib.import_module("slopgate.rules.common")
_shell_read = importlib.import_module("slopgate.rules.common._shell_read")
_cli_lint = importlib.import_module("slopgate.cli.lint")
_quality_lint = importlib.import_module("slopgate.rules.common.quality.lint")
_config_coerce = importlib.import_module("slopgate.config._coerce")
_lint_report = importlib.import_module("slopgate.cli.lint_report")

FlatSiblingFindingInput = _python_ast_rules.FlatSiblingFindingInput
flat_sibling_resolve_candidate_path = (
    _python_ast_rules.flat_sibling_resolve_candidate_path
)
flat_sibling_patch_blob = _python_ast_rules.flat_sibling_patch_blob
PythonFlatFileSiblingsRule = _python_ast_rules.PythonFlatFileSiblingsRule
thin_wrapper_extract_single_call = _python_ast_rules.thin_wrapper_extract_single_call
thin_wrapper_attribute_name = _python_ast_rules.thin_wrapper_attribute_name
thin_wrapper_call_target_name = _python_ast_rules.thin_wrapper_call_target_name
is_test_helper_path = _python_ast_rules.is_test_helper_path
is_wrapper_candidate = _python_ast_rules.is_wrapper_candidate
PythonThinWrapperRule = _python_ast_rules.PythonThinWrapperRule
is_broad_exception = _python_ast_rules.is_broad_exception
is_logger_call = _python_ast_rules.is_logger_call
is_empty_default_return = _python_ast_rules.is_empty_default_return
PythonBroadExceptLoggerRule = _python_ast_rules.PythonBroadExceptLoggerRule
load_toml = _config_io.load_toml
load_json = _config_io.load_json
slopgate_path = _config_io.slopgate_path
slopgate_template = _config_io.slopgate_template
merge_updated_input = _engine_render.merge_updated_input
collect_context = _engine_render.collect_context
top_decision = _engine_render.top_decision
serialize_findings = _engine_render.serialize_findings
resolve_test_file_paths = _test_smells.resolve_test_file_paths
count_sut_calls = _test_smells.count_sut_calls
call_assertion_name = _test_smells.call_assertion_name
is_assertion_call = _test_smells.is_assertion_call
has_assertion = _test_smells.has_assertion
max_bare_assert_run = _test_smells.max_bare_assert_run
hypothesis_properties = _test_smells.hypothesis_properties
hypothesis_score = _test_smells.hypothesis_score
detect_hypothesis_candidates = _test_smells.detect_hypothesis_candidates
missing_import_from_violation = _test_smells.missing_import_from_violation
module_or_package_exists = _test_smells.module_or_package_exists
is_pytest_fixture_decorator = _test_smells.is_pytest_fixture_decorator
is_fixture_support_module = _test_smells.is_fixture_support_module
detect_fixtures_outside_conftest = _test_smells.detect_fixtures_outside_conftest
detect_untested_production_code = _test_smells.detect_untested_production_code
has_token = _test_smells.has_token
integration_seam_score = _test_smells.integration_seam_score
detect_missing_integration_tests = _test_smells.detect_missing_integration_tests
resolve_candidate_path = _git_quality.resolve_candidate_path
git_output = _git_quality.git_output
git_repo_root = _git_quality.git_repo_root
normalize_git_remote = _git_quality.normalize_git_remote
is_worktree = _git_quality.is_worktree
is_slopgate_repo = _git_quality.is_slopgate_repo
default_branch_name = _git_quality.default_branch_name
path_contains_fragment = _infra_security.path_contains_fragment
is_safe_bash_for_path = _infra_security.is_safe_bash_for_path
is_modifying_tool = _infra_security.is_modifying_tool
infra_deny = _infra_security.infra_deny
check_config_path = _infra_security.check_config_path
HookInfraExecProtectionRule = _infra_security.HookInfraExecProtectionRule
add_optional_path_argument = _cli_parsers.add_optional_path_argument
add_dry_run_argument = _cli_parsers.add_dry_run_argument
add_details_argument = _cli_parsers.add_details_argument
RetryLockStateMixin = _locks_store.RetryLockStateMixin
RepairPlanStateMixin = _locks_store.RepairPlanStateMixin
HookStateStore = _locks_store.HookStateStore
collect_quality_commands = _postedit_quality.collect_quality_commands
run_quality_commands = _postedit_quality.run_quality_commands
PostEditQualityRule = _postedit_quality.PostEditQualityRule
RetryLockPayload = _state_models.RetryLockPayload
DenyKeyPattern = _state_models.DenyKeyPattern
HookStateSnapshot = _state_models.HookStateSnapshot
shell_command_executable_paths = _payload_shell.shell_command_executable_paths
shell_tokens = _payload_shell.shell_tokens
shell_command_paths = _payload_shell.shell_command_paths
sensitive_pattern_expr = _sensitive_system_git.sensitive_pattern_expr
compile_sensitive_patterns = _sensitive_system_git.compile_sensitive_patterns
SensitiveDataRule = _sensitive_system_git.SensitiveDataRule
match_system_path = _sensitive_system_git.match_system_path
match_system_command = _sensitive_system_git.match_system_command
detect_git_bypass = _sensitive_system_git.detect_git_bypass
_shell_safe_read = _rules_common._shell_safe_read
path_matches_any = _shell_read.path_matches_any
read_context_fragment = _shell_read.read_context_fragment
discover_project_root = _cli_lint.discover_project_root
lint_check = _cli_lint.lint_check
lint_baseline = _cli_lint.lint_baseline
lint_test_integrity = _cli_lint.lint_test_integrity
SearchReminderRule = _quality_lint.SearchReminderRule
resolve_python_candidates = _quality_lint.resolve_python_candidates
collect_touched_lint_failures = _quality_lint.collect_touched_lint_failures
python_lint_targets = _quality_lint.python_lint_targets
object_dict = _config_coerce.object_dict
string_value = _config_coerce.string_value
bool_value = _config_coerce.bool_value
int_value = _config_coerce.int_value
command_map = _config_coerce.command_map
LintFiles = _lint_report.LintFiles
LintHeader = _lint_report.LintHeader
TallyInput = _lint_report.TallyInput
tally_rule = _lint_report.tally_rule
print_lint_summary = _lint_report.print_lint_summary

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
    _shell_safe_read.command_has_word,
    _shell_safe_read.shell_tokens,
    _shell_safe_read.find_command_has_mutation,
    _shell_safe_read.is_safe_read_shell_command,
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
