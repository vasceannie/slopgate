---
name: gitnexus-area-rules
description: "Skill for the Rules area of slopgate. 170 symbols across 59 files."
---

# Rules

170 symbols | 59 files | Cohesion: 79%

## When to Use

- Working with code in `src/`
- Understanding how RuleList, has_error_signals, RuleInspector work
- Modifying rules-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/rules/langgraph.py` | LangGraphDeprecatedAPIRule, LangGraphStateMutationRule, LangGraphStateReducerRule, _is_langgraph_project, _iter_langgraph_sources (+11) |
| `dashboard/src/components/dashboard/rules/model.ts` | buildRuleMetadata, categorySortIndex, cliUnsupportedReason, formatCliTitle, getCategory (+10) |
| `src/slopgate/rules/error_rules.py` | BashFailureReinforcementRule, BashOutputErrorRule, _active_bash_command, _command_error_context, _extract_bash_output (+6) |
| `src/slopgate/rules/baseline_guard.py` | BaselineGuardRule, _command_name, _is_repo_wide_baseline_command, _looks_like_env_assignment, evaluate (+5) |
| `dashboard/src/components/dashboard/rules/RuleCommandBand.tsx` | CommandTopBar, ExclusionBadgeList, GlobalExclusionsPanel, TopBarActions, TopBarStatus (+4) |
| `dashboard/src/components/dashboard/rules/RuleInspector.tsx` | PathExclusionsSection, HookParamsSection, PlacementSection, RuleIdentitySection, RuleInspector (+4) |
| `src/slopgate/rules/__init__.py` | PythonAstImportFailureRule, _build_python_ast_rules, _import_python_ast_rule_classes, _python_ast_import_failure_rules, build_always_on_rules (+3) |
| `dashboard/src/components/dashboard/rules/RuleList.tsx` | FilterBar, RuleList, grouped, CategoryHeaderRow, RuleIdentityCell (+3) |
| `src/slopgate/rules/regex_rule_matching.py` | matches_text, path_allowed, path_hit, scalar_hit, compile_regex_patterns |
| `src/slopgate/rules/python_ast/_staging/test_smell_rules.py` | PythonAssertionRouletteRule, PythonConditionalAssertionRule, PythonEagerTestRule, PythonFixtureOutsideConftestRule |

## Entry Points

Start here when exploring this area:

- **`RuleList`** (Function) — `dashboard/src/components/dashboard/rules/RuleList.tsx:356`
- **`has_error_signals`** (Function) — `src/slopgate/rules/_error_output_signals.py:38`
- **`RuleInspector`** (Function) — `dashboard/src/components/dashboard/rules/RuleInspector.tsx:414`
- **`grouped`** (Function) — `dashboard/src/components/dashboard/rules/RuleList.tsx:399`
- **`buildRuleMetadata`** (Function) — `dashboard/src/components/dashboard/rules/model.ts:216`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `PythonAstImportFailureRule` | Class | `src/slopgate/rules/__init__.py` | 95 |
| `Rule` | Class | `src/slopgate/rules/base.py` | 12 |
| `BaselineGuardRule` | Class | `src/slopgate/rules/baseline_guard.py` | 103 |
| `GitNoVerifyRule` | Class | `src/slopgate/rules/common/_sensitive_system_git.py` | 229 |
| `SensitiveDataRule` | Class | `src/slopgate/rules/common/_sensitive_system_git.py` | 51 |
| `SystemProtectionRule` | Class | `src/slopgate/rules/common/_sensitive_system_git.py` | 172 |
| `FullFileReadRule` | Class | `src/slopgate/rules/common/_shell_read.py` | 128 |
| `PromptContextRule` | Class | `src/slopgate/rules/common/_shell_read.py` | 81 |
| `ProtectedPathsRule` | Class | `src/slopgate/rules/common/_shell_read.py` | 239 |
| `PostEditLintRule` | Class | `src/slopgate/rules/common/quality/lint.py` | 218 |
| `SearchReminderRule` | Class | `src/slopgate/rules/common/quality/lint.py` | 50 |
| `PostEditQualityRule` | Class | `src/slopgate/rules/common/quality/postedit.py` | 236 |
| `BashFailureReinforcementRule` | Class | `src/slopgate/rules/error_rules.py` | 257 |
| `BashOutputErrorRule` | Class | `src/slopgate/rules/error_rules.py` | 221 |
| `LangGraphDeprecatedAPIRule` | Class | `src/slopgate/rules/langgraph.py` | 309 |
| `LangGraphStateMutationRule` | Class | `src/slopgate/rules/langgraph.py` | 272 |
| `LangGraphStateReducerRule` | Class | `src/slopgate/rules/langgraph.py` | 196 |
| `PythonPytestAsyncioRule` | Class | `src/slopgate/rules/python_ast/_pytest_asyncio.py` | 45 |
| `PythonAstHealthRule` | Class | `src/slopgate/rules/python_ast/_rules/ast_health.py` | 29 |
| `PythonBroadExceptLoggerRule` | Class | `src/slopgate/rules/python_ast/_rules/broad_silent.py` | 63 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Run_rules → _locked_file` | cross_community | 9 |
| `Run_rules → _path_lock_for` | cross_community | 9 |
| `Evaluate → _carrier_text` | cross_community | 8 |
| `Evaluate → _text_from_mapping` | cross_community | 8 |
| `Evaluate → _carrier_text` | cross_community | 8 |
| `Evaluate → _text_from_mapping` | cross_community | 8 |
| `Evaluate → _carrier_text` | cross_community | 8 |
| `Evaluate → _text_from_mapping` | cross_community | 8 |
| `Evaluate → Object_dict` | cross_community | 8 |
| `Evaluate → Object_dict` | cross_community | 8 |

## How to Explore

1. `context({name: "RuleList"})` — see callers and callees
2. `query({search_query: "rules"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
