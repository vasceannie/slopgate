---
name: gitnexus-area-engine
description: "Skill for the Engine area of slopgate. 334 symbols across 53 files."
---

# Engine

334 symbols | 53 files | Cohesion: 70%

## When to Use

- Working with code in `tests/`
- Understanding how assert_bash_negative_case, assert_write_negative_case, test_pi_replace_json_string_edits_block_type_suppression work
- Modifying engine-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/engine/test_07_type_script_rules_to_baseline_warnings.py` | test_linter_shell_edit_denied, test_baseline_cat_no_warn, test_baseline_path_warns, test_baseline_shell_edit_warns, test_config_002_write_denied (+25) |
| `tests/engine/support.py` | _is_not_denied, assert_bash_negative_case, assert_write_negative_case, _set_skip_paths, enable_failing_post_edit_quality_command (+11) |
| `tests/engine/test_09_find_mutations_not_safe_read_to_remind_pytest_multiprocessing.py` | test_find_mutation_on_hook_path_blocked, test_plain_pytest_gets_reminder, test_pytest_with_n_auto_no_reminder, test_pytest_with_n_equals_no_reminder, test_pytest_with_n_number_no_reminder (+9) |
| `tests/engine/test_06_lang_graph_to_py_quality_009.py` | test_py_log_001, test_py_quality_009, test_py_type_002, test_docstring_comment_allowed, test_single_comment_allowed (+8) |
| `tests/engine/test_08_py_quality_010_to_sed_not_safe_read.py` | test_py_quality_010, test_py_quality_011, test_sed_i_blocked_on_protected_path, test_sed_redirect_blocked_on_protected_path, test_sed_without_redirect_blocked_on_protected_path (+8) |
| `tests/test_flat_file_sibling_packages.py` | _bash_package_move_command, _patch_payload, _posttool_write, _write_completed_package_move, bash_payload (+8) |
| `tests/engine/test_10_sensitive_data_safe_suffixes_to_sensitive_data_safe_suffix_edge_cases.py` | test_docker_files_not_blocked, test_dotenv_package_not_blocked, test_env_in_unrelated_path_not_blocked, test_key_example_allowed, test_npmrc_example_allowed (+8) |
| `src/slopgate/engine/_fingerprints.py` | _cached_file_digest, _existing_files, _file_digest, _file_stat_key, guidance_fingerprint (+8) |
| `tests/engine/test_12_enforcement_modes.py` | test_enrolled_repo_subdirectory_stays_repo_strict, test_enrolled_repo_with_noqualitygate_is_relaxed, test_outside_repo_runs_safety_only, test_skip_paths_suppresses_strict_not_safety, test_worktree_auto_enrolls_from_repo_marker (+7) |
| `tests/engine/test_14_result_trace_provenance.py` | _load_runtime_config, test_guidance_change_leaves_policy_fingerprint_stable, test_policy_fingerprint_tracks_rule_enablement, test_regex_rule_message_changes_guidance_fingerprint, test_rule_source_change_alters_policy_fingerprint_without_version_bump (+6) |

## Entry Points

Start here when exploring this area:

- **`assert_bash_negative_case`** (Function) — `tests/engine/support.py:269`
- **`assert_write_negative_case`** (Function) — `tests/engine/support.py:252`
- **`test_pi_replace_json_string_edits_block_type_suppression`** (Function) — `tests/engine/test_02_inline_payload_denies_to_shell_command_paths_ignore_wrapped_absolute_executable_position/test_pi_replace_payloads.py:108`
- **`test_pi_replace_lines_payload_blocks_type_suppression`** (Function) — `tests/engine/test_02_inline_payload_denies_to_shell_command_paths_ignore_wrapped_absolute_executable_position/test_pi_replace_payloads.py:13`
- **`test_pi_transcript_style_replace_arguments_blocks_type_suppression`** (Function) — `tests/engine/test_02_inline_payload_denies_to_shell_command_paths_ignore_wrapped_absolute_executable_position/test_pi_replace_payloads.py:46`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `assert_bash_negative_case` | Function | `tests/engine/support.py` | 269 |
| `assert_write_negative_case` | Function | `tests/engine/support.py` | 252 |
| `test_pi_replace_json_string_edits_block_type_suppression` | Function | `tests/engine/test_02_inline_payload_denies_to_shell_command_paths_ignore_wrapped_absolute_executable_position/test_pi_replace_payloads.py` | 108 |
| `test_pi_replace_lines_payload_blocks_type_suppression` | Function | `tests/engine/test_02_inline_payload_denies_to_shell_command_paths_ignore_wrapped_absolute_executable_position/test_pi_replace_payloads.py` | 13 |
| `test_pi_transcript_style_replace_arguments_blocks_type_suppression` | Function | `tests/engine/test_02_inline_payload_denies_to_shell_command_paths_ignore_wrapped_absolute_executable_position/test_pi_replace_payloads.py` | 46 |
| `test_absolute_find_executable_after_shell_separator_is_not_system_path_target` | Function | `tests/engine/test_02_inline_payload_denies_to_shell_command_paths_ignore_wrapped_absolute_executable_position/test_protected_paths.py` | 150 |
| `test_absolute_search_executable_path_is_not_system_path_target` | Function | `tests/engine/test_02_inline_payload_denies_to_shell_command_paths_ignore_wrapped_absolute_executable_position/test_protected_paths.py` | 141 |
| `test_posttool_bash_reason_paths_do_not_trigger_ast_read_errors` | Function | `tests/engine/test_03_posttool_bash_reason_paths_do_not_trigger_ast_read_errors_to_edge_cases.py` | 58 |
| `test_two_asserts_below_threshold` | Function | `tests/engine/test_03_posttool_bash_reason_paths_do_not_trigger_ast_read_errors_to_edge_cases.py` | 193 |
| `test_small_file_no_warn` | Function | `tests/engine/test_04_baseline_guard_to_disabled_rule_does_not_fire.py` | 189 |
| `test_python_ast_parse_failure_skips_virtualenv_paths` | Function | `tests/engine/test_05_build_rules_survives_python_ast_import_error_to_output_json_serialisable_by_fixture.py` | 112 |
| `test_py_log_001` | Function | `tests/engine/test_06_lang_graph_to_py_quality_009.py` | 188 |
| `test_py_quality_009` | Function | `tests/engine/test_06_lang_graph_to_py_quality_009.py` | 247 |
| `test_py_type_002` | Function | `tests/engine/test_06_lang_graph_to_py_quality_009.py` | 212 |
| `test_linter_shell_edit_denied` | Function | `tests/engine/test_07_type_script_rules_to_baseline_warnings.py` | 220 |
| `test_py_quality_010` | Function | `tests/engine/test_08_py_quality_010_to_sed_not_safe_read.py` | 36 |
| `test_py_quality_011` | Function | `tests/engine/test_08_py_quality_010_to_sed_not_safe_read.py` | 151 |
| `test_post_edit_lint_rule_skips_virtualenv_lib_inspection` | Function | `tests/engine/test_virtualenv_path_exclusions.py` | 17 |
| `test_python_ast_parse_failure_skips_dot_venvs_paths` | Function | `tests/engine/test_virtualenv_path_exclusions.py` | 47 |
| `write_slopgate` | Function | `tests/engine/test_virtualenv_path_exclusions.py` | 9 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Cmd_replay → _locked_file` | cross_community | 9 |
| `Cmd_replay → _path_lock_for` | cross_community | 9 |
| `Evaluate_hook_request → _locked_file` | cross_community | 9 |
| `Evaluate_hook_request → _path_lock_for` | cross_community | 9 |
| `Run_rules → _locked_file` | cross_community | 9 |
| `Run_rules → _path_lock_for` | cross_community | 9 |
| `Cmd_replay → Is_windows` | cross_community | 8 |
| `Evaluate_hook_request → Is_windows` | cross_community | 8 |
| `Cmd_daemon → Reset_request_analysis_cache` | cross_community | 7 |
| `Enrich_findings → _locked_file` | cross_community | 7 |

## How to Explore

1. `context({name: "assert_bash_negative_case"})` — see callers and callees
2. `query({search_query: "engine"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
