---
name: gitnexus-area-integration
description: "Skill for the Integration area of slopgate. 133 symbols across 18 files."
---

# Integration

133 symbols | 18 files | Cohesion: 92%

## When to Use

- Working with code in `tests/`
- Understanding how apply_ast_rule_config_overrides, context_with_limits, test_broad_and_silent_exception_rules_report_distinct_findings work
- Modifying integration-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/integration/test_opencode_plugin_control_contract.py` | _run_plugin_contract, _write_fake_slopgate, _write_plugin_runner, test_file_edited_block_is_logged_without_throwing, test_generated_plugin_allows_unknown_read_only_tool (+14) |
| `tests/integration/test_guard_rule_public_api.py` | bash_payload, context_for_payload, test_baseline_guard_blocks_populated_baseline_creation, test_config_change_guard_rule_blocks_disable_all_hooks, test_git_no_verify_rule_blocks_hook_bypass (+12) |
| `tests/integration/test_python_ast_rule_public_api.py` | context_with_limits, test_broad_and_silent_exception_rules_report_distinct_findings, test_complexity_rule_reports_target_function, test_dead_code_rule_reports_unreachable_function, test_deep_nesting_rule_reports_nested_function (+9) |
| `tests/integration/test_opencode_plugin_repair_gate.py` | _run_pending_repair_file_tool, _write_fake_slopgate, test_opencode_toml_header_comments_preserve_relaxed_repo_mode, test_pending_repair_allows_bootstrap_when_status_is_unavailable, test_pending_repair_allows_direct_file_repair_tool (+5) |
| `tests/integration/test_rule_enrichment_installer_pipeline.py` | _render_context, _render_findings, _rendered_text, test_adapter_render_request_pipeline_extracts_event_and_findings, test_render_output_pipeline_orders_denial_context_before_advisory_debt (+4) |
| `tests/integration/test_python_ast_staging_public_api.py` | test_assertion_roulette_rule_reports_bare_assert_run, test_conditional_assertion_rule_reports_control_flow, test_duplicate_call_sequence_rule_reports_shared_sequence, test_eager_test_rule_reports_excess_sut_calls, test_fixture_outside_conftest_rule_reports_fixture_function (+3) |
| `tests/integration/test_cli_hook_runtime.py` | _run_handle_with_daemon, test_cmd_handle_does_not_fallback_after_daemon_accept_failure, test_cmd_handle_fails_closed_for_accepted_daemon_error, test_cmd_handle_preserves_daemon_request_platform, test_cmd_handle_preserves_daemon_stderr_and_exit_code (+3) |
| `tests/integration/test_stats_improvement_pipeline.py` | _result, test_integration_comparison_excludes_legacy_rows_from_cohorts, test_integration_comparison_filters_and_builds_matching_sides, test_integration_comparison_supports_rule_and_confidence_cohorts, test_integration_multi_rule_paths_are_rule_local (+3) |
| `tests/integration/test_opencode_plugin_capability_contract.py` | _run_plugin_with_real_slopgate, test_generated_plugin_allows_declared_remote_effects_in_clean_state, test_generated_plugin_allows_known_read_only_tool, test_generated_plugin_allows_task_delegation, test_generated_plugin_allows_unprojected_read_only_mcp_tool (+2) |
| `tests/integration/test_opencode_tool_capability_parity.py` | _evaluate_capability_case, _prepare_repo, _runner_source, capability_payload, prepare_repair_state (+2) |

## Entry Points

Start here when exploring this area:

- **`apply_ast_rule_config_overrides`** (Function) — `tests/integration/config_override_support.py:56`
- **`context_with_limits`** (Function) — `tests/integration/test_python_ast_rule_public_api.py:33`
- **`test_broad_and_silent_exception_rules_report_distinct_findings`** (Function) — `tests/integration/test_python_ast_rule_public_api.py:49`
- **`test_complexity_rule_reports_target_function`** (Function) — `tests/integration/test_python_ast_rule_public_api.py:78`
- **`test_dead_code_rule_reports_unreachable_function`** (Function) — `tests/integration/test_python_ast_rule_public_api.py:102`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `apply_ast_rule_config_overrides` | Function | `tests/integration/config_override_support.py` | 56 |
| `context_with_limits` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 33 |
| `test_broad_and_silent_exception_rules_report_distinct_findings` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 49 |
| `test_complexity_rule_reports_target_function` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 78 |
| `test_dead_code_rule_reports_unreachable_function` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 102 |
| `test_deep_nesting_rule_reports_nested_function` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 158 |
| `test_feature_envy_rule_reports_external_object_bias` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 197 |
| `test_flat_sibling_rule_reports_projected_package_sprawl` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 313 |
| `test_import_alias_rule_reports_non_standard_alias` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 256 |
| `test_import_fanout_rule_reports_excess_from_imports` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 266 |
| `test_long_line_rule_reports_executable_line` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 178 |
| `test_long_method_rule_reports_function_span` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 119 |
| `test_long_parameter_rule_reports_function_signature` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 140 |
| `test_private_import_chain_rule_reports_stacked_private_import` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 283 |
| `test_thin_wrapper_rule_reports_structural_smell` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 222 |
| `test_assertion_roulette_rule_reports_bare_assert_run` | Function | `tests/integration/test_python_ast_staging_public_api.py` | 116 |
| `test_conditional_assertion_rule_reports_control_flow` | Function | `tests/integration/test_python_ast_staging_public_api.py` | 151 |
| `test_duplicate_call_sequence_rule_reports_shared_sequence` | Function | `tests/integration/test_python_ast_staging_public_api.py` | 43 |
| `test_eager_test_rule_reports_excess_sut_calls` | Function | `tests/integration/test_python_ast_staging_public_api.py` | 97 |
| `test_fixture_outside_conftest_rule_reports_fixture_function` | Function | `tests/integration/test_python_ast_staging_public_api.py` | 134 |

## How to Explore

1. `context({name: "apply_ast_rule_config_overrides"})` — see callers and callees
2. `query({search_query: "integration"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
