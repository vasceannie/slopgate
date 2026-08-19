---
name: tests
description: "Skill for the Tests area of slopgate. 883 symbols across 113 files."
---

# Tests

883 symbols | 113 files | Cohesion: 91%

## When to Use

- Working with code in `tests/`
- Understanding how assert_write_negative_case, assert_bash_negative_case, write_slopgate work
- Modifying tests-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/test_regex_targets.py` | bash_payload, test_shell_set_plus_e_denied, test_shell_stderr_suppression_gets_exact_repair_pattern, test_safe_command_no_shell_rule, test_py_shell_src_sed_edit_denied (+25) |
| `tests/test_error_and_config_rules.py` | _post_bash, test_traceback_detected, test_test_failure_detected, _pre_bash, _pre_write (+18) |
| `tests/test_lint_source_detector_public_api.py` | parsed_file, test_semantic_clone_detector_reports_structurally_identical_functions, test_broad_except_detector_reports_swallowed_default_return, test_silent_fallback_detector_reports_datetime_now_return, test_silent_except_detector_reports_empty_broad_handler (+16) |
| `tests/test_stats.py` | _analyze, _pair_counts, string_list, _entry, test_counts_deny_decision (+14) |
| `tests/test_harness_schema_context.py` | _fixture, _mapping, _string_set, _source, test_harness_schema_context_sources_are_official_available_and_parsable (+14) |
| `tests/test_installer.py` | hook_commands, command_includes_slopgate_handle, existing_claude_settings, existing_codex_hooks, installed_hook_commands (+13) |
| `tests/test_hot_rule_recommendation_gate.py` | enroll_repo, write_payload, additional_context, _pathless_quality_output, _assert_pathless_quality_fallback (+13) |
| `tests/test_lint_cli_rule_enablement.py` | _collector_map, _write_global_config, _regex_rule_payload, test_rule_surface_cli_enablement_runs_content_regex_rule_as_lint_collector, test_regex_rule_collectors_directly_exposes_content_rule_violations (+13) |
| `tests/test_enrichment_public_api.py` | context_for_source, test_logger_enricher_reports_project_logging_abstractions, test_silent_except_enricher_reports_called_functions, test_python_any_enricher_reports_dict_and_callback_guidance, test_type_suppression_enricher_reports_specific_advice (+12) |
| `tests/daemon_protocol/support.py` | __call__, wait_started, release, _started_event, _release_event (+12) |

## Entry Points

Start here when exploring this area:

- **`assert_write_negative_case`** (Function) — `tests/engine/support.py:252`
- **`assert_bash_negative_case`** (Function) — `tests/engine/support.py:269`
- **`write_slopgate`** (Function) — `tests/engine/test_virtualenv_path_exclusions.py:9`
- **`test_post_edit_lint_rule_skips_virtualenv_lib_inspection`** (Function) — `tests/engine/test_virtualenv_path_exclusions.py:17`
- **`test_python_ast_parse_failure_skips_dot_venvs_paths`** (Function) — `tests/engine/test_virtualenv_path_exclusions.py:47`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `assert_write_negative_case` | Function | `tests/engine/support.py` | 252 |
| `assert_bash_negative_case` | Function | `tests/engine/support.py` | 269 |
| `write_slopgate` | Function | `tests/engine/test_virtualenv_path_exclusions.py` | 9 |
| `test_post_edit_lint_rule_skips_virtualenv_lib_inspection` | Function | `tests/engine/test_virtualenv_path_exclusions.py` | 17 |
| `test_python_ast_parse_failure_skips_dot_venvs_paths` | Function | `tests/engine/test_virtualenv_path_exclusions.py` | 47 |
| `finding_ids` | Function | `tests/support.py` | 155 |
| `bash_payload` | Function | `tests/test_flat_file_sibling_packages.py` | 26 |
| `test_posttool_blocks_existing_plain_prefix_cluster` | Function | `tests/test_flat_file_sibling_packages.py` | 102 |
| `test_pretool_allows_mechanical_bash_move_into_package` | Function | `tests/test_flat_file_sibling_packages.py` | 116 |
| `test_posttool_allows_completed_bash_move_into_package` | Function | `tests/test_flat_file_sibling_packages.py` | 135 |
| `test_pretool_allows_single_patch_that_converts_cluster_to_package` | Function | `tests/test_flat_file_sibling_packages.py` | 145 |
| `test_pretool_still_blocks_patch_that_leaves_flat_cluster` | Function | `tests/test_flat_file_sibling_packages.py` | 184 |
| `test_posttool_bash_still_blocks_cluster_left_after_command` | Function | `tests/test_flat_file_sibling_packages.py` | 210 |
| `test_quality_lint_reference_tests_ignore_changed_scope_for_touched_source` | Function | `tests/test_quality_lint_scope_references.py` | 44 |
| `bash_payload` | Function | `tests/test_regex_targets.py` | 21 |
| `test_enrichment_helper_pipeline_reads_context_and_files` | Function | `tests/integration/test_helper_seam_contracts.py` | 34 |
| `test_pytest_asyncio_config_reads_pytest_ini` | Function | `tests/integration/test_pytest_asyncio_public_api.py` | 113 |
| `test_source_parse_pipeline_counts_and_extracts_functions` | Function | `tests/integration/test_refactored_module_seams.py` | 69 |
| `test_enrichment_helpers_read_target_content` | Function | `tests/test_enrichment_helpers_public_api.py` | 27 |
| `test_find_local_call_sites_skips_current_and_hidden_files` | Function | `tests/test_enrichment_helpers_public_api.py` | 76 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Build_standalone | 5 calls |
| Rules | 4 calls |
| Engine | 2 calls |
| _rules | 2 calls |
| Adapters | 1 calls |
| Util | 1 calls |
| Forcedash_server | 1 calls |
| Quality | 1 calls |

## How to Explore

1. `context({name: "assert_write_negative_case"})` — see callers and callees
2. `query({search_query: "tests"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
