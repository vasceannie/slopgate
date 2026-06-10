"""Static reference coverage for refactored public module surfaces."""

from __future__ import annotations

from slopgate.engine._hints import (
    rule_hint,
    failure_class,
    finding_path,
    denial_context,
    retry_budget_relevant_denials,
)
from slopgate.engine._runner import (
    platform_capability,
    EvalAccumulator,
    resolve_enforcement_mode,
    run_rules,
)
from slopgate.lint._details._metadata import (
    line_number,
    location,
    signature,
    metadata_lines,
)
from slopgate.lint._details._prognosis import prognosis
import slopgate.lint._details._test_context
from slopgate.lint._detectors.test_smells._assertion_core import (
    dotted_name,
    call_tail,
    iter_tests,
    is_none_constant,
    is_true_constant,
    is_zero_constant,
    is_len_call,
    is_weak_compare,
    expr_preview,
)
from slopgate.lint._detectors.test_smells._coverage_helpers import (
    metadata_int,
    coverage_rel_path,
    coverage_percent_from_summary,
    coverage_percent_from_json_file,
    CoverageInputs,
    static_coverage_violation,
)
from slopgate.lint._detectors.test_smells import _payload_core
from slopgate.lint._detectors.test_smells._payload_core import (
    assigned_names,
    semantic_assertion_lines,
    is_type_narrowing_guard,
    cast_target_name,
    is_low_risk_cast_target,
    is_high_risk_cast_target,
    contains_token,
    patch_target_is_internal,
    string_arg,
)
from slopgate.rules.common._quality_lint_guidance import (
    lint_target_summary,
    lint_check_instruction,
    has_oversized_module_failure,
    first_lint_path,
    lint_split_scenario,
)
from slopgate.rules.python_ast._rules._boundary_helpers import (
    path_parts,
    is_test_module_path,
    attribute_chain_parts,
    called_name,
    has_boundary_log_call,
    function_name_has_event_signal,
    BoundaryFunction,
)
from slopgate.rules.python_ast._rules._import_helpers import (
    import_alias_full_name,
    allowed_import_alias,
    import_alias_replacement,
    is_private_module_segment,
    private_module_segments,
    imported_modules,
)
from slopgate.rules.python_ast._rules._module_size_guidance import (
    module_split_scenario,
    oversized_module_split_guidance,
)
from slopgate.rules.python_ast._rules._module_size_sources import (
    is_line_count_camouflage,
    read_python_source,
    project_replacement,
    is_authored_python_path,
    project_top_level_edit,
    dedupe_sources,
)
from slopgate.rules.python_ast._staging.duplicate_rules._shared import finding_count
from slopgate.state._files import StateFileMixin, StateSnapshotMixin
from slopgate.state._keys import (
    failure_count,
    StateKeyMixin,
    SessionStateMutationMixin,
    FullReadStateMixin,
    SearchReminderStateMixin,
)
from slopgate.util.payloads._targets import (
    tool_input_path,
    tool_input_content_target,
    multi_edit_content_targets,
    patch_content_targets,
    unique_content_targets,
    direct_candidate_paths,
)
from slopgate.lint._detectors.duplicates._semantic import (
    Normalizer,
    normalize_ast,
    structure_hash,
    is_import_stmt,
    is_future_import,
    import_section,
    canonical_alias,
    detect_semantic_clones,
)
from slopgate.rules.python_ast._rules._source_parse import (
    parse_strict,
    first_significant_line,
    looks_like_indented_fragment,
    parse_health_failure,
    resolve_python_path,
    line_count,
    parsed_functions,
)
from slopgate.rules.stop_rules._enrollment import (
    enrollment_basename,
    is_delete_like_tool,
    patch_touches_enrollment_marker,
    repo_enrollment_sentinel_finding,
    RepoEnrollmentProtectionRule,
)
from slopgate.lint._detectors.duplicates._literals import (
    collect_literals,
    is_semantic_string_literal,
    constant_location,
    string_literal_metadata,
    detect_repeated_literals,
)
from slopgate.lint._detectors.test_smells._production_symbols import (
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
    symbol_is_referenced,
)
from slopgate.lint._detectors.test_smells import _production_symbols
from slopgate.engine._retry import (
    dedupe_findings,
    filter_search_reminder_dedupe,
    apply_loop_aware_steering,
    inject_recent_failure_context,
    enforce_retry_budget,
)

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
    "_test_context": (slopgate.lint._details._test_context.test_context_lines,),
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
    "_coverage_helpers": (
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
    "_quality_lint_guidance": (
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
    "_targets": (
        tool_input_path,
        tool_input_content_target,
        multi_edit_content_targets,
        patch_content_targets,
        unique_content_targets,
        direct_candidate_paths,
    ),
    "_semantic": (
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
    "_literals": (
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
