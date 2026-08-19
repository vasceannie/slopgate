---
name: rules
description: "Skill for the _rules area of slopgate. 191 symbols across 39 files."
---

# _rules

191 symbols | 39 files | Cohesion: 85%

## When to Use

- Working with code in `src/`
- Understanding how is_rule_enabled, read_context_fragment, evaluate_common work
- Modifying _rules-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/rules/python_ast/_rules/_method_style.py` | PythonLongMethodRule, PythonLongParameterRule, PythonLongLineRule, PythonDeepNestingRule, evaluate (+12) |
| `src/slopgate/rules/python_ast/_rules/_wrapper_god.py` | PythonThinWrapperRule, PythonGodClassRule, evaluate, _non_dunder_method_count, _check_source (+11) |
| `src/slopgate/rules/python_ast/_rules/_flat_siblings.py` | PythonFlatFileSiblingsRule, flat_sibling_resolve_candidate_path, flat_sibling_patch_blob, flat_sibling_patch_added_and_removed_paths, flat_sibling_projected_removed_files (+10) |
| `src/slopgate/rules/python_ast/_staging/test_smell_rules.py` | PythonEagerTestRule, PythonAssertionRouletteRule, PythonFixtureOutsideConftestRule, PythonConditionalAssertionRule, evaluate (+6) |
| `src/slopgate/rules/python_ast/_rules/_source_parse.py` | first_significant_line, looks_like_indented_fragment, parse_health_failure, is_full_module_candidate, resolve_python_path (+6) |
| `src/slopgate/rules/python_ast/_rules/_boundary_helpers.py` | path_parts, attribute_chain_parts, called_name, function_name_has_event_signal, contains_event_boundary_call (+6) |
| `src/slopgate/rules/python_ast/_rules/_complexity_dead.py` | PythonCyclomaticComplexityRule, PythonDeadCodeRule, evaluate, evaluate, _complexity (+5) |
| `src/slopgate/rules/stop_rules/_git_quality.py` | IgnorePreexistingRule, RequireQualityCheckRule, WarnLargeFileRule, tail_read, extract_content_text (+5) |
| `src/slopgate/rules/python_ast/_rules/_broad_silent.py` | PythonBroadExceptLoggerRule, PythonSilentExceptRule, evaluate, evaluate, is_broad_exception (+4) |
| `src/slopgate/rules/python_ast/_rules/_ast_health.py` | PythonAstHealthRule, _recovery_text, finding, _pre_content_failure, _post_path_failure (+3) |

## Entry Points

Start here when exploring this area:

- **`is_rule_enabled`** (Function) — `src/slopgate/rules/base.py:29`
- **`read_context_fragment`** (Function) — `src/slopgate/rules/common/_shell_read.py:69`
- **`evaluate_common`** (Function) — `src/slopgate/rules/python_ast/_helpers.py:93`
- **`tail_read`** (Function) — `src/slopgate/rules/stop_rules/_git_quality.py:147`
- **`extract_content_text`** (Function) — `src/slopgate/rules/stop_rules/_git_quality.py:157`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `PythonAstImportFailureRule` | Class | `src/slopgate/rules/__init__.py` | 94 |
| `Rule` | Class | `src/slopgate/rules/base.py` | 12 |
| `BaselineGuardRule` | Class | `src/slopgate/rules/baseline_guard.py` | 103 |
| `SensitiveDataRule` | Class | `src/slopgate/rules/common/_sensitive_system_git.py` | 51 |
| `SystemProtectionRule` | Class | `src/slopgate/rules/common/_sensitive_system_git.py` | 172 |
| `GitNoVerifyRule` | Class | `src/slopgate/rules/common/_sensitive_system_git.py` | 229 |
| `PromptContextRule` | Class | `src/slopgate/rules/common/_shell_read.py` | 81 |
| `FullFileReadRule` | Class | `src/slopgate/rules/common/_shell_read.py` | 128 |
| `ProtectedPathsRule` | Class | `src/slopgate/rules/common/_shell_read.py` | 239 |
| `SearchReminderRule` | Class | `src/slopgate/rules/common/quality/lint.py` | 47 |
| `PostEditLintRule` | Class | `src/slopgate/rules/common/quality/lint.py` | 215 |
| `PostEditQualityRule` | Class | `src/slopgate/rules/common/quality/postedit.py` | 236 |
| `BashOutputErrorRule` | Class | `src/slopgate/rules/error_rules.py` | 221 |
| `BashFailureReinforcementRule` | Class | `src/slopgate/rules/error_rules.py` | 257 |
| `LangGraphStateReducerRule` | Class | `src/slopgate/rules/langgraph.py` | 196 |
| `LangGraphStateMutationRule` | Class | `src/slopgate/rules/langgraph.py` | 272 |
| `LangGraphDeprecatedAPIRule` | Class | `src/slopgate/rules/langgraph.py` | 309 |
| `PythonPytestAsyncioRule` | Class | `src/slopgate/rules/python_ast/_pytest_asyncio.py` | 45 |
| `PythonAstHealthRule` | Class | `src/slopgate/rules/python_ast/_rules/_ast_health.py` | 29 |
| `PythonBoundaryLoggingRule` | Class | `src/slopgate/rules/python_ast/_rules/_boundary_rule.py` | 27 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Evaluate → _module_name_for_package` | cross_community | 5 |
| `Evaluate → Decision_for_context` | cross_community | 4 |
| `Evaluate → Prefix_for_name` | cross_community | 4 |
| `Evaluate → Is_rule_enabled` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Duplicate_rules | 6 calls |
| Quality | 2 calls |
| Size | 2 calls |
| Python_ast | 1 calls |

## How to Explore

1. `context({name: "is_rule_enabled"})` — see callers and callees
2. `query({search_query: "_rules"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
