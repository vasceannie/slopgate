---
name: rules-2
description: "Skill for the Rules area of slopgate. 103 symbols across 25 files."
---

# Rules

103 symbols | 25 files | Cohesion: 71%

## When to Use

- Working with code in `dashboard/`
- Understanding how RuleList, has_error_signals, hasAnyPrefix work
- Modifying rules-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `dashboard/src/components/dashboard/rules/model.ts` | hasAnyPrefix, cliUnsupportedReason, formatCliTitle, hookCounterpartsForCli, hookEventsForRule (+10) |
| `dashboard/src/components/dashboard/rules/RuleCommandBand.tsx` | TopBarStatus, TopBarActions, CommandTopBar, ExclusionBadgeList, GlobalExclusionsPanel (+4) |
| `dashboard/src/components/dashboard/rules/RuleInspector.tsx` | PathExclusionsSection, RuleIdentitySection, PlacementSection, HookParamsSection, useRuleInspectorState (+4) |
| `src/slopgate/rules/error_rules.py` | _is_read_only_command, _strip_command_wrapper, _is_benign_failure, _safe_command_excerpt, _command_error_context (+4) |
| `src/slopgate/rules/baseline_guard.py` | _extract_rules_dict, _parse_json_dict, _find_increases, _resolve_existing_path, _check_baseline_change (+4) |
| `dashboard/src/components/dashboard/rules/RuleList.tsx` | FilterBar, RuleList, grouped, StatusCell, RuleIdentityCell (+3) |
| `src/slopgate/rules/langgraph.py` | _is_langgraph_project, is_langgraph_context, _read_source, _iter_langgraph_sources, evaluate (+3) |
| `src/slopgate/rules/__init__.py` | __init__, _python_ast_import_failure_rules, _import_python_ast_rule_classes, _build_python_ast_rules, build_always_on_rules (+2) |
| `src/slopgate/rules/regex_rule_matching.py` | path_allowed, matches_text, path_hit, scalar_hit, compile_regex_patterns |
| `dashboard/src/components/dashboard/rules/RuleWorkbench.tsx` | useMobileViewport, useRuleMetadataWithChanges, useKeyDown, RuleWorkbench |

## Entry Points

Start here when exploring this area:

- **`RuleList`** (Function) — `dashboard/src/components/dashboard/rules/RuleList.tsx:356`
- **`has_error_signals`** (Function) — `src/slopgate/rules/_error_output_signals.py:38`
- **`hasAnyPrefix`** (Function) — `dashboard/src/components/dashboard/rules/model.ts:99`
- **`cliUnsupportedReason`** (Function) — `dashboard/src/components/dashboard/rules/model.ts:103`
- **`formatCliTitle`** (Function) — `dashboard/src/components/dashboard/rules/model.ts:114`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `RuleList` | Function | `dashboard/src/components/dashboard/rules/RuleList.tsx` | 356 |
| `has_error_signals` | Function | `src/slopgate/rules/_error_output_signals.py` | 38 |
| `hasAnyPrefix` | Function | `dashboard/src/components/dashboard/rules/model.ts` | 99 |
| `cliUnsupportedReason` | Function | `dashboard/src/components/dashboard/rules/model.ts` | 103 |
| `formatCliTitle` | Function | `dashboard/src/components/dashboard/rules/model.ts` | 114 |
| `hookCounterpartsForCli` | Function | `dashboard/src/components/dashboard/rules/model.ts` | 125 |
| `hookEventsForRule` | Function | `dashboard/src/components/dashboard/rules/model.ts` | 156 |
| `getCategory` | Function | `dashboard/src/components/dashboard/rules/model.ts` | 186 |
| `categorySortIndex` | Function | `dashboard/src/components/dashboard/rules/model.ts` | 195 |
| `buildRuleMetadata` | Function | `dashboard/src/components/dashboard/rules/model.ts` | 216 |
| `grouped` | Function | `dashboard/src/components/dashboard/rules/RuleList.tsx` | 399 |
| `RuleInspector` | Function | `dashboard/src/components/dashboard/rules/RuleInspector.tsx` | 414 |
| `directHookRuleCliCounterparts` | Function | `dashboard/src/components/dashboard/rules/model.ts` | 121 |
| `surfaceHookEnabled` | Function | `dashboard/src/components/dashboard/rules/model.ts` | 131 |
| `surfaceCliEnabled` | Function | `dashboard/src/components/dashboard/rules/model.ts` | 138 |
| `getCliRuleIds` | Function | `dashboard/src/components/dashboard/rules/model.ts` | 201 |
| `getCliDefaultEnabled` | Function | `dashboard/src/components/dashboard/rules/model.ts` | 210 |
| `getRuleChangedFields` | Function | `dashboard/src/components/dashboard/rules/model.ts` | 312 |
| `getPendingChangesList` | Function | `dashboard/src/components/dashboard/rules/model.ts` | 357 |
| `pendingList` | Function | `dashboard/src/components/dashboard/rules/RuleCommandBand.tsx` | 369 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `RuleWorkbench → DirectHookRuleCliCounterparts` | cross_community | 5 |
| `Ast_src_collectors → _is_langgraph_project` | cross_community | 5 |
| `RuleCommandBand → Cn` | cross_community | 5 |
| `RuleInspector → Cn` | cross_community | 4 |
| `RuleWorkbench → SurfaceHookEnabled` | cross_community | 4 |
| `RuleWorkbench → SurfaceCliEnabled` | cross_community | 4 |
| `RuleWorkbench → HookEventsForRule` | cross_community | 4 |
| `Evaluate → _is_langgraph_project` | intra_community | 4 |
| `PathExplorer → Cn` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Ui | 14 calls |
| _rules | 4 calls |
| Util | 3 calls |
| _detectors | 2 calls |
| Search | 2 calls |
| Engine | 1 calls |
| Dashboard | 1 calls |

## How to Explore

1. `context({name: "RuleList"})` — see callers and callees
2. `query({search_query: "rules"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
