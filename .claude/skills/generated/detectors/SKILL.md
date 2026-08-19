---
name: detectors
description: "Skill for the _detectors area of slopgate. 98 symbols across 16 files."
---

# _detectors

98 symbols | 16 files | Cohesion: 83%

## When to Use

- Working with code in `src/`
- Understanding how ast_src_collectors, get_config, detect_broad_except_swallow work
- Modifying _detectors-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/lint/_detectors/source_interop.py` | _parsed_files, detect_feature_envy, _statement_blocks, _first_dead_code, detect_dead_code (+10) |
| `src/slopgate/lint/_detectors/exception_safety.py` | _is_broad_except, detect_broad_except_swallow, _is_datetime_now_return, detect_silent_fallback, detect_silent_except (+7) |
| `src/slopgate/lint/_detectors/type_safety.py` | _get_compiled_patterns, detect_type_suppressions, _find_comment_start, _inside_type_checking, _annotation_contains_any (+7) |
| `src/slopgate/lint/_detectors/declarative.py` | is_constant_name, is_declarative_constant_value, _call_name, _is_type_expr, _is_declarative_join_call (+7) |
| `src/slopgate/lint/_detectors/code_smells.py` | _detector_state, _complexity, detect_high_complexity, detect_long_methods, detect_too_many_params (+3) |
| `src/slopgate/lint/_detectors/logging_conventions.py` | _is_in_infrastructure, detect_direct_get_logger, detect_wrong_logger_name, _wrong_logger_name_violation, _wrong_logger_name_violations (+2) |
| `src/slopgate/lint/_detectors/wrappers.py` | detect_unnecessary_wrappers, _single_delegated_call, _delegatable_params, _is_passthrough_arg, _is_passthrough_keyword (+2) |
| `src/slopgate/rules/langgraph.py` | _is_typed_dict_base, _is_bare_list_annotation, _is_annotated_wrapper, _bare_list_fields, find_reducer_findings (+1) |
| `src/slopgate/lint/_detectors/langgraph.py` | _source, _langgraph_files, detect_langgraph_state_reducers, detect_langgraph_state_mutations, detect_langgraph_builder_api |
| `src/slopgate/lint/_collector_groups/source.py` | ast_src_collectors, _source_interop_collectors, _code_smell_collectors |

## Entry Points

Start here when exploring this area:

- **`ast_src_collectors`** (Function) — `src/slopgate/lint/_collector_groups/source.py:11`
- **`get_config`** (Function) — `src/slopgate/lint/_config.py:160`
- **`detect_broad_except_swallow`** (Function) — `src/slopgate/lint/_detectors/exception_safety.py:134`
- **`detect_silent_fallback`** (Function) — `src/slopgate/lint/_detectors/exception_safety.py:200`
- **`detect_silent_except`** (Function) — `src/slopgate/lint/_detectors/exception_safety.py:268`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `ast_src_collectors` | Function | `src/slopgate/lint/_collector_groups/source.py` | 11 |
| `get_config` | Function | `src/slopgate/lint/_config.py` | 160 |
| `detect_broad_except_swallow` | Function | `src/slopgate/lint/_detectors/exception_safety.py` | 134 |
| `detect_silent_fallback` | Function | `src/slopgate/lint/_detectors/exception_safety.py` | 200 |
| `detect_silent_except` | Function | `src/slopgate/lint/_detectors/exception_safety.py` | 268 |
| `detect_langgraph_state_reducers` | Function | `src/slopgate/lint/_detectors/langgraph.py` | 51 |
| `detect_langgraph_state_mutations` | Function | `src/slopgate/lint/_detectors/langgraph.py` | 72 |
| `detect_langgraph_builder_api` | Function | `src/slopgate/lint/_detectors/langgraph.py` | 93 |
| `detect_long_lines` | Function | `src/slopgate/lint/_detectors/line_length.py` | 23 |
| `detect_direct_get_logger` | Function | `src/slopgate/lint/_detectors/logging_conventions.py` | 40 |
| `detect_wrong_logger_name` | Function | `src/slopgate/lint/_detectors/logging_conventions.py` | 82 |
| `is_logger_call` | Function | `src/slopgate/lint/_detectors/logging_conventions.py` | 190 |
| `detect_stale_patterns` | Function | `src/slopgate/lint/_detectors/stale_code.py` | 17 |
| `is_pytest_fixture_decorator` | Function | `src/slopgate/lint/_detectors/test_smells/_fixtures.py` | 15 |
| `is_fixture_support_module` | Function | `src/slopgate/lint/_detectors/test_smells/_fixtures.py` | 35 |
| `detect_fixtures_outside_conftest` | Function | `src/slopgate/lint/_detectors/test_smells/_fixtures.py` | 41 |
| `detect_type_suppressions` | Function | `src/slopgate/lint/_detectors/type_safety.py` | 208 |
| `detect_unnecessary_wrappers` | Function | `src/slopgate/lint/_detectors/wrappers.py` | 97 |
| `src_root` | Function | `src/slopgate/lint/_helpers/paths.py` | 13 |
| `tests_root` | Function | `src/slopgate/lint/_helpers/paths.py` | 21 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Detect_semantic_clones → Object_dict` | cross_community | 7 |
| `Detect_semantic_clones → _coerce_path_entries` | cross_community | 6 |
| `Detect_semantic_clones → _resolve_path_entries` | cross_community | 6 |
| `Ast_src_collectors → _path_values` | cross_community | 6 |
| `Ast_src_collectors → _threshold_values` | cross_community | 6 |
| `Run_test_integrity_collectors → _path_values` | cross_community | 6 |
| `Run_test_integrity_collectors → _threshold_values` | cross_community | 6 |
| `Run_test_integrity_collectors → _allowlist_values` | cross_community | 6 |
| `Run_test_integrity_collectors → _logging_values` | cross_community | 6 |
| `Detect_repeated_literals → _path_values` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| _helpers | 2 calls |
| Imports | 2 calls |
| Lint | 1 calls |
| Duplicates | 1 calls |
| Rules | 1 calls |
| _rules | 1 calls |

## How to Explore

1. `context({name: "ast_src_collectors"})` — see callers and callees
2. `query({search_query: "_detectors"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
