---
name: integration
description: "Skill for the Integration area of slopgate. 79 symbols across 11 files."
---

# Integration

79 symbols | 11 files | Cohesion: 96%

## When to Use

- Working with code in `tests/`
- Understanding how apply_ast_rule_config_overrides, context_with_limits, test_broad_and_silent_exception_rules_report_distinct_findings work
- Modifying integration-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/integration/test_python_ast_rule_public_api.py` | context_with_limits, test_broad_and_silent_exception_rules_report_distinct_findings, test_complexity_rule_reports_target_function, test_dead_code_rule_reports_unreachable_function, test_long_method_rule_reports_function_span (+12) |
| `tests/integration/test_guard_rule_public_api.py` | context_for_payload, write_payload, bash_payload, test_baseline_guard_blocks_populated_baseline_creation, test_search_reminder_reports_grep_without_search_tool (+12) |
| `tests/integration/test_rule_enrichment_installer_pipeline.py` | _render_context, _render_findings, _rendered_text, test_adapter_render_request_pipeline_extracts_event_and_findings, test_render_output_pipeline_orders_denial_context_before_advisory_debt (+4) |
| `tests/integration/test_python_ast_staging_public_api.py` | test_repeated_blocks_rule_reports_first_repeated_scope, test_duplicate_call_sequence_rule_reports_shared_sequence, test_repeated_magic_number_rule_reports_worst_numeric_literal, test_semantic_clone_rule_reports_structural_clone_pair, test_eager_test_rule_reports_excess_sut_calls (+3) |
| `tests/integration/test_cli_hook_runtime.py` | _run_handle_with_daemon, test_cmd_handle_uses_configured_resident_daemon, test_cmd_handle_preserves_daemon_request_platform, test_cmd_handle_uses_default_socket_when_present, test_cmd_handle_uses_linux_runtime_socket_when_env_is_missing (+3) |
| `tests/integration/test_pytest_asyncio_public_api.py` | async_function_at, test_pytest_asyncio_ast_helpers_detect_aliases_and_marked_tests, test_pytest_asyncio_ast_helpers_detect_fixture_decorator_details, test_fixture_check_target_preserves_ast_context, first_async_function (+1) |
| `tests/integration/test_guard_rule_langgraph_public_api.py` | langgraph_context, test_langgraph_state_reducer_rule_reports_bare_list_field, test_langgraph_state_mutation_rule_reports_direct_state_change, test_langgraph_deprecated_api_rule_reports_old_entrypoint_api |
| `tests/integration/test_opencode_daemon_reachability.py` | _linux_runtime_socket_path, _opencode_status_payload, _run_opencode_daemon_handoff, test_opencode_handle_reaches_resident_linux_runtime_daemon |
| `tests/integration/config_override_support.py` | apply_ast_rule_config_overrides, apply_guard_rule_config_overrides |
| `tests/integration/test_helper_seam_contracts.py` | _adapter_permission_pipeline_summary, test_adapter_permission_pipeline_renders_context_and_decisions |

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
| `test_long_method_rule_reports_function_span` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 119 |
| `test_long_parameter_rule_reports_function_signature` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 140 |
| `test_deep_nesting_rule_reports_nested_function` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 158 |
| `test_long_line_rule_reports_executable_line` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 178 |
| `test_feature_envy_rule_reports_external_object_bias` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 197 |
| `test_thin_wrapper_rule_reports_structural_smell` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 222 |
| `test_god_class_rule_reports_structural_smell` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 236 |
| `test_import_alias_rule_reports_non_standard_alias` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 256 |
| `test_import_fanout_rule_reports_excess_from_imports` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 266 |
| `test_private_import_chain_rule_reports_stacked_private_import` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 283 |
| `test_ast_health_rule_reports_invalid_python_content` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 300 |
| `test_flat_sibling_rule_reports_projected_package_sprawl` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 313 |
| `test_module_size_rule_reports_oversized_content` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 327 |
| `test_repeated_blocks_rule_reports_first_repeated_scope` | Function | `tests/integration/test_python_ast_staging_public_api.py` | 20 |
| `test_duplicate_call_sequence_rule_reports_shared_sequence` | Function | `tests/integration/test_python_ast_staging_public_api.py` | 43 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 2 calls |

## How to Explore

1. `context({name: "apply_ast_rule_config_overrides"})` — see callers and callees
2. `query({search_query: "integration"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
