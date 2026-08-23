---
name: gitnexus-area-detectors
description: "Skill for the _detectors area of slopgate. 137 symbols across 29 files."
---

# _detectors

137 symbols | 29 files | Cohesion: 80%

## When to Use

- Working with code in `src/`
- Understanding how ast_src_collector_specs, test_collector_specs, test_collectors work
- Modifying _detectors-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/lint/_detectors/test_smells/_basic_detection.py` | _parsed_test_files, call_assertion_name, conditional_assertion_line, contains_assert, count_sut_calls (+10) |
| `src/slopgate/lint/_detectors/declarative.py` | _call_name, _is_declarative_assign, _is_declarative_cast_call, _is_declarative_constant_call, _is_declarative_constructor_call (+9) |
| `src/slopgate/lint/_detectors/source_interop.py` | _first_dead_code, _flat_sibling_names, _flat_sibling_prefix, _has_same_named_package, _parsed_files (+9) |
| `src/slopgate/lint/_detectors/exception_safety.py` | _is_broad_except, _is_datetime_now_return, detect_broad_except_swallow, detect_silent_except, detect_silent_fallback (+7) |
| `src/slopgate/lint/_detectors/type_safety.py` | _find_comment_start, _get_compiled_patterns, detect_any_usage, detect_type_suppressions, _annotation_contains_any (+7) |
| `src/slopgate/lint/_detectors/code_smells.py` | _complexity, _detector_state, _max_nesting, detect_deep_nesting, detect_god_classes (+4) |
| `src/slopgate/lint/_detectors/logging_conventions.py` | _is_in_infrastructure, detect_direct_get_logger, detect_wrong_logger_name, _collect_wrong_logger_name_violations, _wrong_logger_name_violation (+2) |
| `src/slopgate/lint/_detectors/wrappers.py` | detect_unnecessary_wrappers, _delegatable_params, _is_passthrough_arg, _is_passthrough_keyword, _is_simple_delegation (+2) |
| `src/slopgate/lint/_helpers/ast_utils.py` | enclosing_function, _span_lines, class_body_lines, count_methods, function_body_lines (+1) |
| `src/slopgate/lint/_detectors/langgraph.py` | _langgraph_files, _source, detect_langgraph_builder_api, detect_langgraph_state_mutations, detect_langgraph_state_reducers |

## Entry Points

Start here when exploring this area:

- **`ast_src_collector_specs`** (Function) — `src/slopgate/lint/_collector_groups/ast_collectors.py:9`
- **`test_collector_specs`** (Function) — `src/slopgate/lint/_collector_groups/pytest_file_collectors.py:9`
- **`test_collectors`** (Function) — `src/slopgate/lint/_collector_groups/pytest_file_collectors.py:45`
- **`cli_collector_specs`** (Function) — `src/slopgate/lint/_collector_groups/runner_specs.py:39`
- **`source_analysis`** (Function) — `src/slopgate/lint/_collector_groups/source.py:12`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `ast_src_collector_specs` | Function | `src/slopgate/lint/_collector_groups/ast_collectors.py` | 9 |
| `test_collector_specs` | Function | `src/slopgate/lint/_collector_groups/pytest_file_collectors.py` | 9 |
| `test_collectors` | Function | `src/slopgate/lint/_collector_groups/pytest_file_collectors.py` | 45 |
| `cli_collector_specs` | Function | `src/slopgate/lint/_collector_groups/runner_specs.py` | 39 |
| `source_analysis` | Function | `src/slopgate/lint/_collector_groups/source.py` | 12 |
| `parsed_groups` | Function | `src/slopgate/lint/_collector_groups/source_prepare.py` | 54 |
| `project_scope_hits` | Function | `src/slopgate/lint/_collector_groups/source_prepare.py` | 102 |
| `get_config` | Function | `src/slopgate/lint/_config.py` | 160 |
| `detect_duplicate_call_sequences` | Function | `src/slopgate/lint/_detectors/duplicates/blocks.py` | 99 |
| `detect_repeated_blocks` | Function | `src/slopgate/lint/_detectors/duplicates/blocks.py` | 57 |
| `detect_broad_except_swallow` | Function | `src/slopgate/lint/_detectors/exception_safety.py` | 134 |
| `detect_silent_except` | Function | `src/slopgate/lint/_detectors/exception_safety.py` | 268 |
| `detect_silent_fallback` | Function | `src/slopgate/lint/_detectors/exception_safety.py` | 200 |
| `detect_langgraph_builder_api` | Function | `src/slopgate/lint/_detectors/langgraph.py` | 93 |
| `detect_langgraph_state_mutations` | Function | `src/slopgate/lint/_detectors/langgraph.py` | 72 |
| `detect_langgraph_state_reducers` | Function | `src/slopgate/lint/_detectors/langgraph.py` | 51 |
| `detect_long_lines` | Function | `src/slopgate/lint/_detectors/line_length.py` | 23 |
| `detect_direct_get_logger` | Function | `src/slopgate/lint/_detectors/logging_conventions.py` | 40 |
| `detect_wrong_logger_name` | Function | `src/slopgate/lint/_detectors/logging_conventions.py` | 82 |
| `detect_stale_patterns` | Function | `src/slopgate/lint/_detectors/stale_code.py` | 17 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Select_tests_for_changed_files → Object_dict` | cross_community | 10 |
| `Cli_collector_specs → String_list` | cross_community | 10 |
| `Cli_collector_specs → Load_toml` | cross_community | 10 |
| `Cli_collector_specs → _paths_section` | cross_community | 10 |
| `Cli_collector_specs → Resolve_root_paths` | cross_community | 10 |
| `Cli_collector_specs → _global_enabled_cli_rules` | cross_community | 10 |
| `Cli_collector_specs → _global_surface_cli_rules` | cross_community | 10 |
| `Cli_collector_specs → _repo_enabled_cli_rules` | cross_community | 10 |
| `Cli_collector_specs → _repo_surface_cli_rules` | cross_community | 10 |
| `Cli_collector_specs → _allowlist_values` | cross_community | 10 |

## How to Explore

1. `context({name: "ast_src_collector_specs"})` — see callers and callees
2. `query({search_query: "_detectors"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
