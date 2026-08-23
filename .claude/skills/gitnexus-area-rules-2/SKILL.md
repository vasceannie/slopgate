---
name: gitnexus-area-rules-2
description: "Skill for the _rules area of slopgate. 79 symbols across 31 files."
---

# _rules

79 symbols | 31 files | Cohesion: 65%

## When to Use

- Working with code in `src/`
- Understanding how is_rule_enabled, read_context_fragment, evaluate_common work
- Modifying _rules-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/rules/python_ast/_rules/source_parse.py` | first_significant_line, is_full_module_candidate, line_count, looks_like_indented_fragment, parse_health_failure (+5) |
| `src/slopgate/rules/python_ast/_rules/complexity_dead.py` | evaluate, evaluate, _check_source, _complexity, _check_source (+3) |
| `src/slopgate/rules/python_ast/_rules/broad_silent.py` | evaluate, evaluate, is_broad_exception, is_empty_default_return, is_logger_call (+2) |
| `src/slopgate/rules/python_ast/_rules/ast_health.py` | _evaluate_post, _evaluate_pre, _post_path_failure, _pre_content_failure, _recovery_text (+2) |
| `src/slopgate/rules/python_ast/_rules/feature_envy.py` | evaluate, _check_function, _check_source, _count_envy_accesses, _param_names (+1) |
| `src/slopgate/rules/python_ast/_rules/private_imports.py` | evaluate, _check_source, _path_finding, finding |
| `src/slopgate/rules/python_ast/_staging/test_smell_rules.py` | evaluate, evaluate, evaluate, evaluate |
| `src/slopgate/rules/python_ast/_rules/style_limits/nesting.py` | evaluate, _check_source, _max_nesting |
| `src/slopgate/rules/python_ast/_rules/class_shape/god.py` | _check_source, _non_dunder_method_count, evaluate |
| `src/slopgate/rules/common/_shell_read.py` | read_context_fragment, evaluate |

## Entry Points

Start here when exploring this area:

- **`is_rule_enabled`** (Function) — `src/slopgate/rules/base.py:29`
- **`read_context_fragment`** (Function) — `src/slopgate/rules/common/_shell_read.py:69`
- **`evaluate_common`** (Function) — `src/slopgate/rules/python_ast/_helpers.py:93`
- **`is_security_doc_or_example`** (Function) — `src/slopgate/rules/stop_rules/_infra_security.py:134`
- **`collect_git_context`** (Function) — `src/slopgate/rules/stop_rules/_session_config.py:22`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `is_rule_enabled` | Function | `src/slopgate/rules/base.py` | 29 |
| `read_context_fragment` | Function | `src/slopgate/rules/common/_shell_read.py` | 69 |
| `evaluate_common` | Function | `src/slopgate/rules/python_ast/_helpers.py` | 93 |
| `is_security_doc_or_example` | Function | `src/slopgate/rules/stop_rules/_infra_security.py` | 134 |
| `collect_git_context` | Function | `src/slopgate/rules/stop_rules/_session_config.py` | 22 |
| `is_line_count_camouflage` | Function | `src/slopgate/rules/python_ast/_rules/module/size/sources.py` | 30 |
| `first_significant_line` | Function | `src/slopgate/rules/python_ast/_rules/source_parse.py` | 27 |
| `is_full_module_candidate` | Function | `src/slopgate/rules/python_ast/_rules/source_parse.py` | 64 |
| `line_count` | Function | `src/slopgate/rules/python_ast/_rules/source_parse.py` | 104 |
| `looks_like_indented_fragment` | Function | `src/slopgate/rules/python_ast/_rules/source_parse.py` | 36 |
| `parse_health_failure` | Function | `src/slopgate/rules/python_ast/_rules/source_parse.py` | 44 |
| `resolve_python_path` | Function | `src/slopgate/rules/python_ast/_rules/source_parse.py` | 96 |
| `test_ast_health_rule_reports_invalid_python_content` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 300 |
| `parsed_classes` | Function | `src/slopgate/rules/python_ast/_rules/source_parse.py` | 125 |
| `parsed_nodes` | Function | `src/slopgate/rules/python_ast/_rules/source_parse.py` | 109 |
| `python_ast_rule_is_disabled` | Function | `src/slopgate/rules/python_ast/_rules/source_parse.py` | 131 |
| `test_god_class_rule_reports_structural_smell` | Function | `tests/integration/test_python_ast_rule_public_api.py` | 236 |
| `is_broad_exception` | Function | `src/slopgate/rules/python_ast/_rules/broad_silent.py` | 25 |
| `is_empty_default_return` | Function | `src/slopgate/rules/python_ast/_rules/broad_silent.py` | 49 |
| `is_logger_call` | Function | `src/slopgate/rules/python_ast/_rules/broad_silent.py` | 39 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Pre_python_camouflage_sources → Resolve_python_path` | cross_community | 5 |
| `Evaluate → Is_rule_enabled` | cross_community | 3 |
| `Flat_sibling_projected_removed_files → First_present` | cross_community | 3 |

## How to Explore

1. `context({name: "is_rule_enabled"})` — see callers and callees
2. `query({search_query: "_rules"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
