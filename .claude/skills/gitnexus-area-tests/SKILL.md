---
name: gitnexus-area-tests
description: "Skill for the Tests area of slopgate. 984 symbols across 135 files."
---

# Tests

984 symbols | 135 files | Cohesion: 90%

## When to Use

- Working with code in `tests/`
- Understanding how test_exec_protection_bash_touch_makefile, test_protected_path_makefile, test_large_file_warns work
- Modifying tests-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/test_regex_targets.py` | test_git_no_verify_denial_gives_safe_commit_command, test_shell_stderr_suppression_gets_exact_repair_pattern, bash_payload, test_git_commit_gets_context, test_py_shell_automation_perl_edit_denied (+24) |
| `tests/test_lint_source_detector_public_api.py` | parsed_file, test_boundary_logging_detector_ignores_logged_boundary, test_boundary_logging_detector_reports_unlogged_event_boundary, test_broad_except_detector_reports_swallowed_default_return, test_dead_code_detector_reports_unreachable_statement (+16) |
| `tests/test_harness_schema_context.py` | _assert_claude_event_surface_matches_contract, _expected_contract_note_flags, _fixture, _mapping, _source (+14) |
| `tests/test_stats.py` | _pair_counts, _assert_enrichment_stats, _mixed_enrichment_stats, test_churn_metrics_include_repeated_deny_rates, test_daily_counts (+14) |
| `tests/test_stats_improvement.py` | _persistence_payload, _strict_entry, test_repeated_denial_persistence_denominator, test_repeated_denial_persistence_rate, test_still_failing_and_persistence (+14) |
| `tests/test_hot_rule_recommendation_gate.py` | _assert_pathless_quality_fallback, _pathless_quality_output, test_quality_lint_pathless_reason_names_last_edit_fallback, _assert_boundary_allowlist_context, additional_context (+13) |
| `tests/test_repair_cli.py` | _capture_scoped_lint, _expected_path_capture, _mark_repair, _required, _verify (+13) |
| `tests/test_installer.py` | command_includes_slopgate_handle, existing_claude_settings, existing_codex_hooks, hook_commands, installed_hook_commands (+13) |
| `tests/test_lint_cli_rule_enablement.py` | _collector_map, _regex_rule_payload, _write_global_config, test_command_regex_rule_is_not_exposed_as_batch_lint_collector, test_regex_rule_collectors_directly_exposes_content_rule_violations (+13) |
| `tests/test_enrichment_public_api.py` | context_for_source, test_complexity_enricher_ignores_incomplete_metadata_property, test_feature_envy_enricher_ignores_incomplete_metadata_property, test_logger_enricher_reports_project_logging_abstractions, test_python_any_enricher_ignores_irrelevant_content_property (+12) |

## Entry Points

Start here when exploring this area:

- **`test_exec_protection_bash_touch_makefile`** (Function) — `tests/engine/test_02_inline_payload_denies_to_shell_command_paths_ignore_wrapped_absolute_executable_position/test_protected_paths.py:193`
- **`test_protected_path_makefile`** (Function) — `tests/engine/test_02_inline_payload_denies_to_shell_command_paths_ignore_wrapped_absolute_executable_position/test_protected_paths.py:19`
- **`test_large_file_warns`** (Function) — `tests/engine/test_04_baseline_guard_to_disabled_rule_does_not_fire.py:181`
- **`test_permission_request_asks_for_makefile`** (Function) — `tests/engine/test_04_baseline_guard_to_disabled_rule_does_not_fire.py:21`
- **`test_prompt_injects_context`** (Function) — `tests/engine/test_04_baseline_guard_to_disabled_rule_does_not_fire.py:35`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `test_exec_protection_bash_touch_makefile` | Function | `tests/engine/test_02_inline_payload_denies_to_shell_command_paths_ignore_wrapped_absolute_executable_position/test_protected_paths.py` | 193 |
| `test_protected_path_makefile` | Function | `tests/engine/test_02_inline_payload_denies_to_shell_command_paths_ignore_wrapped_absolute_executable_position/test_protected_paths.py` | 19 |
| `test_large_file_warns` | Function | `tests/engine/test_04_baseline_guard_to_disabled_rule_does_not_fire.py` | 181 |
| `test_permission_request_asks_for_makefile` | Function | `tests/engine/test_04_baseline_guard_to_disabled_rule_does_not_fire.py` | 21 |
| `test_prompt_injects_context` | Function | `tests/engine/test_04_baseline_guard_to_disabled_rule_does_not_fire.py` | 35 |
| `test_sessionstart_injects_git_context` | Function | `tests/engine/test_04_baseline_guard_to_disabled_rule_does_not_fire.py` | 124 |
| `test_sessionstart_injects_git_context_from_worktree` | Function | `tests/engine/test_04_baseline_guard_to_disabled_rule_does_not_fire.py` | 135 |
| `test_permission_request_uses_decision_behavior` | Function | `tests/engine/test_05_build_rules_survives_python_ast_import_error_to_output_json_serialisable_by_fixture.py` | 202 |
| `test_pretooluse_uses_hookSpecificOutput` | Function | `tests/engine/test_05_build_rules_survives_python_ast_import_error_to_output_json_serialisable_by_fixture.py` | 195 |
| `assert_asked_by` | Function | `tests/support.py` | 118 |
| `hook_output` | Function | `tests/support.py` | 71 |
| `nested_output` | Function | `tests/support.py` | 76 |
| `required_string` | Function | `tests/support.py` | 86 |
| `test_hook_fixture_denial_mentions_support_modules` | Function | `tests/test_fixture_support_policy.py` | 122 |
| `test_quality_lint_pathless_reason_names_last_edit_fallback` | Function | `tests/test_hot_rule_recommendation_gate.py` | 185 |
| `test_clean_output_no_trigger` | Function | `tests/test_quality_command_output_guidance.py` | 94 |
| `test_isx_lint_alias_gets_full_lint_guidance` | Function | `tests/test_quality_command_output_guidance.py` | 72 |
| `test_quality_lint_tail_output_gets_full_lint_guidance` | Function | `tests/test_quality_command_output_guidance.py` | 23 |
| `test_read_only_command_skipped` | Function | `tests/test_quality_command_output_guidance.py` | 83 |
| `test_vfc_lint_alias_gets_full_lint_guidance` | Function | `tests/test_quality_command_output_guidance.py` | 61 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Main → Coerce_object_dict` | cross_community | 6 |
| `Main → _trim_text` | cross_community | 6 |
| `Evaluate → Object_dict` | cross_community | 6 |
| `Main → Coerce_str_list` | cross_community | 5 |
| `Main → _platform_value` | cross_community | 5 |
| `Evaluate → _prune_counter_map` | cross_community | 5 |
| `Evaluate → Is_object_dict` | cross_community | 5 |
| `Main → Classify` | cross_community | 4 |
| `Evaluate → _acquire_lock` | cross_community | 4 |
| `Evaluate → _release_lock` | cross_community | 4 |

## How to Explore

1. `context({name: "test_exec_protection_bash_touch_makefile"})` — see callers and callees
2. `query({search_query: "tests"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
