"""Static reference coverage for refactored public module surfaces."""

from __future__ import annotations

import importlib


_slopgate_import_0 = importlib.import_module("slopgate.engine._hints")
rule_hint = _slopgate_import_0.rule_hint
failure_class = _slopgate_import_0.failure_class
finding_path = _slopgate_import_0.finding_path
denial_context = _slopgate_import_0.denial_context
retry_budget_relevant_denials = _slopgate_import_0.retry_budget_relevant_denials
_slopgate_import_1 = importlib.import_module("slopgate.engine._runner")
platform_capability = _slopgate_import_1.platform_capability
EvalAccumulator = _slopgate_import_1.EvalAccumulator
resolve_enforcement_mode = _slopgate_import_1.resolve_enforcement_mode
run_rules = _slopgate_import_1.run_rules
_slopgate_import_2 = importlib.import_module("slopgate.lint._details")
line_number = _slopgate_import_2.line_number
location = _slopgate_import_2.location
signature = _slopgate_import_2.signature
metadata_lines = _slopgate_import_2.metadata_lines
_slopgate_import_3 = importlib.import_module("slopgate.lint._details")
prognosis = _slopgate_import_3.prognosis
_slopgate_import_4 = importlib.import_module("slopgate.lint._detectors.test_smells")
dotted_name = _slopgate_import_4.dotted_name
call_tail = _slopgate_import_4.call_tail
iter_tests = _slopgate_import_4.iter_tests
is_none_constant = _slopgate_import_4.is_none_constant
is_true_constant = _slopgate_import_4.is_true_constant
is_zero_constant = _slopgate_import_4.is_zero_constant
is_len_call = _slopgate_import_4.is_len_call
is_weak_compare = _slopgate_import_4.is_weak_compare
expr_preview = _slopgate_import_4.expr_preview
_slopgate_import_5 = importlib.import_module(
    "slopgate.lint._detectors.test_smells.coverage"
)
metadata_int = _slopgate_import_5.metadata_int
coverage_rel_path = _slopgate_import_5.coverage_rel_path
coverage_percent_from_summary = _slopgate_import_5.coverage_percent_from_summary
coverage_percent_from_json_file = _slopgate_import_5.coverage_percent_from_json_file
CoverageInputs = _slopgate_import_5.CoverageInputs
static_coverage_violation = _slopgate_import_5.static_coverage_violation
_slopgate_import_6 = importlib.import_module("slopgate.lint._detectors.test_smells")
_payload_core = _slopgate_import_6._payload_core
_slopgate_import_7 = importlib.import_module("slopgate.lint._detectors.test_smells")
assigned_names = _slopgate_import_7.assigned_names
semantic_assertion_lines = _slopgate_import_7.semantic_assertion_lines
is_type_narrowing_guard = _slopgate_import_7.is_type_narrowing_guard
cast_target_name = _slopgate_import_7.cast_target_name
is_low_risk_cast_target = _slopgate_import_7.is_low_risk_cast_target
is_high_risk_cast_target = _slopgate_import_7.is_high_risk_cast_target
contains_token = _slopgate_import_7.contains_token
patch_target_is_internal = _slopgate_import_7.patch_target_is_internal
string_arg = _slopgate_import_7.string_arg
_slopgate_import_8 = importlib.import_module("slopgate.rules.common.quality.guidance")
lint_target_summary = _slopgate_import_8.lint_target_summary
lint_check_instruction = _slopgate_import_8.lint_check_instruction
has_oversized_module_failure = _slopgate_import_8.has_oversized_module_failure
first_lint_path = _slopgate_import_8.first_lint_path
lint_split_scenario = _slopgate_import_8.lint_split_scenario
_slopgate_import_9 = importlib.import_module("slopgate.rules.python_ast._rules")
path_parts = _slopgate_import_9.path_parts
is_test_module_path = _slopgate_import_9.is_test_module_path
attribute_chain_parts = _slopgate_import_9.attribute_chain_parts
called_name = _slopgate_import_9.called_name
has_boundary_log_call = _slopgate_import_9.has_boundary_log_call
function_name_has_event_signal = _slopgate_import_9.function_name_has_event_signal
BoundaryFunction = _slopgate_import_9.BoundaryFunction
_slopgate_import_10 = importlib.import_module("slopgate.rules.python_ast._rules")
import_alias_full_name = _slopgate_import_10.import_alias_full_name
allowed_import_alias = _slopgate_import_10.allowed_import_alias
import_alias_replacement = _slopgate_import_10.import_alias_replacement
is_private_module_segment = _slopgate_import_10.is_private_module_segment
private_module_segments = _slopgate_import_10.private_module_segments
imported_modules = _slopgate_import_10.imported_modules
_slopgate_import_11 = importlib.import_module("slopgate.rules.python_ast._rules")
module_split_scenario = _slopgate_import_11.module_split_scenario
oversized_module_split_guidance = _slopgate_import_11.oversized_module_split_guidance
_slopgate_import_12 = importlib.import_module("slopgate.rules.python_ast._rules")
is_line_count_camouflage = _slopgate_import_12.is_line_count_camouflage
read_python_source = _slopgate_import_12.read_python_source
project_replacement = _slopgate_import_12.project_replacement
is_authored_python_path = _slopgate_import_12.is_authored_python_path
project_top_level_edit = _slopgate_import_12.project_top_level_edit
dedupe_sources = _slopgate_import_12.dedupe_sources
_slopgate_import_13 = importlib.import_module("slopgate.state._files")
StateFileMixin = _slopgate_import_13.StateFileMixin
StateSnapshotMixin = _slopgate_import_13.StateSnapshotMixin
_slopgate_import_14 = importlib.import_module("slopgate.state._keys")
failure_count = _slopgate_import_14.failure_count
StateKeyMixin = _slopgate_import_14.StateKeyMixin
SessionStateMutationMixin = _slopgate_import_14.SessionStateMutationMixin
FullReadStateMixin = _slopgate_import_14.FullReadStateMixin
SearchReminderStateMixin = _slopgate_import_14.SearchReminderStateMixin
_slopgate_import_15 = importlib.import_module("slopgate.util.payloads.targets")
tool_input_path = _slopgate_import_15.tool_input_path
tool_input_content_target = _slopgate_import_15.tool_input_content_target
multi_edit_content_targets = _slopgate_import_15.multi_edit_content_targets
patch_content_targets = _slopgate_import_15.patch_content_targets
unique_content_targets = _slopgate_import_15.unique_content_targets
direct_candidate_paths = _slopgate_import_15.direct_candidate_paths
_slopgate_import_16 = importlib.import_module(
    "slopgate.lint._detectors.duplicates.semantic"
)
Normalizer = _slopgate_import_16.Normalizer
normalize_ast = _slopgate_import_16.normalize_ast
structure_hash = _slopgate_import_16.structure_hash
is_import_stmt = _slopgate_import_16.is_import_stmt
is_future_import = _slopgate_import_16.is_future_import
import_section = _slopgate_import_16.import_section
canonical_alias = _slopgate_import_16.canonical_alias
detect_semantic_clones = _slopgate_import_16.detect_semantic_clones
_slopgate_import_17 = importlib.import_module("slopgate.rules.python_ast._rules")
parse_strict = _slopgate_import_17.parse_strict
first_significant_line = _slopgate_import_17.first_significant_line
looks_like_indented_fragment = _slopgate_import_17.looks_like_indented_fragment
parse_health_failure = _slopgate_import_17.parse_health_failure
resolve_python_path = _slopgate_import_17.resolve_python_path
line_count = _slopgate_import_17.line_count
parsed_functions = _slopgate_import_17.parsed_functions
_slopgate_import_18 = importlib.import_module("slopgate.rules.stop_rules._enrollment")
enrollment_basename = _slopgate_import_18.enrollment_basename
is_delete_like_tool = _slopgate_import_18.is_delete_like_tool
patch_touches_enrollment_marker = _slopgate_import_18.patch_touches_enrollment_marker
repo_enrollment_sentinel_finding = _slopgate_import_18.repo_enrollment_sentinel_finding
RepoEnrollmentProtectionRule = _slopgate_import_18.RepoEnrollmentProtectionRule
_slopgate_import_19 = importlib.import_module(
    "slopgate.lint._detectors.duplicates.literals"
)
collect_literals = _slopgate_import_19.collect_literals
is_semantic_string_literal = _slopgate_import_19.is_semantic_string_literal
constant_location = _slopgate_import_19.constant_location
string_literal_metadata = _slopgate_import_19.string_literal_metadata
detect_repeated_literals = _slopgate_import_19.detect_repeated_literals
_slopgate_import_20 = importlib.import_module("slopgate.lint._detectors.test_smells")
ProductionSymbol = _slopgate_import_20.ProductionSymbol
module_name_from_rel = _slopgate_import_20.module_name_from_rel
public_top_level_defs = _slopgate_import_20.public_top_level_defs
decorator_texts = _slopgate_import_20.decorator_texts
docstring_text = _slopgate_import_20.docstring_text
replacement_hint = _slopgate_import_20.replacement_hint
branch_score = _slopgate_import_20.branch_score
production_symbols = _slopgate_import_20.production_symbols
module_names = _slopgate_import_20.module_names
reference_tokens_for_tree = _slopgate_import_20.reference_tokens_for_tree
symbol_is_referenced = _slopgate_import_20.symbol_is_referenced
_slopgate_import_21 = importlib.import_module("slopgate.lint._detectors.test_smells")
_production_symbols = _slopgate_import_21._production_symbols
_slopgate_import_22 = importlib.import_module("slopgate.engine._retry")
dedupe_findings = _slopgate_import_22.dedupe_findings
filter_search_reminder_dedupe = _slopgate_import_22.filter_search_reminder_dedupe
apply_loop_aware_steering = _slopgate_import_22.apply_loop_aware_steering
inject_recent_failure_context = _slopgate_import_22.inject_recent_failure_context
enforce_retry_budget = _slopgate_import_22.enforce_retry_budget
_slopgate_details = importlib.import_module("slopgate.lint._details")
_test_context_lines = _slopgate_details.test_context_lines

finding_count = importlib.import_module(
    "slopgate.rules.python_ast._staging.duplicate_rules._shared"
).finding_count

PUBLIC_SYMBOL_GROUPS_a: dict[str, tuple[object, ...]] = {
    "_hints": (
        rule_hint,
        failure_class,
        finding_path,
        denial_context,
        retry_budget_relevant_denials,
    ),
    "_runner": (
        platform_capability,
        EvalAccumulator,
        resolve_enforcement_mode,
        run_rules,
    ),
    "_metadata": (line_number, location, signature, metadata_lines),
    "_prognosis": (prognosis,),
    "_test_context": (_test_context_lines,),
    "_assertion_core": (
        dotted_name,
        call_tail,
        iter_tests,
        is_none_constant,
        is_true_constant,
        is_zero_constant,
        is_len_call,
        is_weak_compare,
        expr_preview,
    ),
    "coverage": (
        metadata_int,
        coverage_rel_path,
        coverage_percent_from_summary,
        coverage_percent_from_json_file,
        CoverageInputs,
        static_coverage_violation,
    ),
    "_payload_core": (
        assigned_names,
        semantic_assertion_lines,
        is_type_narrowing_guard,
        cast_target_name,
        is_low_risk_cast_target,
        is_high_risk_cast_target,
        _payload_core.test_context_text,
        contains_token,
        patch_target_is_internal,
        string_arg,
    ),
    "quality_guidance": (
        lint_target_summary,
        lint_check_instruction,
        has_oversized_module_failure,
        first_lint_path,
        lint_split_scenario,
    ),
    "_boundary_helpers": (
        path_parts,
        is_test_module_path,
        attribute_chain_parts,
        called_name,
        has_boundary_log_call,
        function_name_has_event_signal,
        BoundaryFunction,
    ),
    "_import_helpers": (
        import_alias_full_name,
        allowed_import_alias,
        import_alias_replacement,
        is_private_module_segment,
        private_module_segments,
        imported_modules,
    ),
    "_module_size_guidance": (module_split_scenario, oversized_module_split_guidance),
    "_module_size_sources": (
        is_line_count_camouflage,
        read_python_source,
        project_replacement,
        is_authored_python_path,
        project_top_level_edit,
        dedupe_sources,
    ),
    "_shared": (finding_count,),
    "_files": (StateFileMixin, StateSnapshotMixin),
    "_keys": (
        failure_count,
        StateKeyMixin,
        SessionStateMutationMixin,
        FullReadStateMixin,
        SearchReminderStateMixin,
    ),
    "targets": (
        tool_input_path,
        tool_input_content_target,
        multi_edit_content_targets,
        patch_content_targets,
        unique_content_targets,
        direct_candidate_paths,
    ),
    "semantic": (
        Normalizer,
        normalize_ast,
        structure_hash,
        is_import_stmt,
        is_future_import,
        import_section,
        canonical_alias,
        detect_semantic_clones,
    ),
    "_source_parse": (
        parse_strict,
        first_significant_line,
        looks_like_indented_fragment,
        parse_health_failure,
        resolve_python_path,
        line_count,
        parsed_functions,
    ),
    "_enrollment": (
        enrollment_basename,
        is_delete_like_tool,
        patch_touches_enrollment_marker,
        repo_enrollment_sentinel_finding,
        RepoEnrollmentProtectionRule,
    ),
    "literals": (
        collect_literals,
        is_semantic_string_literal,
        constant_location,
        string_literal_metadata,
        detect_repeated_literals,
    ),
    "_production_symbols": (
        ProductionSymbol,
        module_name_from_rel,
        public_top_level_defs,
        decorator_texts,
        docstring_text,
        replacement_hint,
        branch_score,
        production_symbols,
        module_names,
        reference_tokens_for_tree,
        _production_symbols.test_reference_tokens,
        symbol_is_referenced,
    ),
    "_retry": (
        dedupe_findings,
        filter_search_reminder_dedupe,
        apply_loop_aware_steering,
        inject_recent_failure_context,
        enforce_retry_budget,
    ),
}


def test_refactored_public_symbols_are_importable_a() -> None:
    observed = {name: len(symbols) for name, symbols in PUBLIC_SYMBOL_GROUPS_a.items()}
    assert all(count > 0 for count in observed.values())
    assert len(observed) == len(PUBLIC_SYMBOL_GROUPS_a)
