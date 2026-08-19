---
name: engine
description: "Skill for the Engine area of slopgate. 125 symbols across 29 files."
---

# Engine

125 symbols | 29 files | Cohesion: 85%

## When to Use

- Working with code in `tests/`
- Understanding how evaluate_payload, dedupe_findings, filter_search_reminder_dedupe work
- Modifying engine-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/engine/_retry.py` | dedupe_findings, filter_search_reminder_dedupe, inject_recent_failure_context, _retry_budget_block, enforce_retry_budget (+10) |
| `tests/engine/support.py` | write_slopgate, write_config_from_defaults, _set_skip_paths, write_skip_paths_config, mutate (+7) |
| `src/slopgate/engine/_runner.py` | resolve_enforcement_mode, _apply_severity_overrides, _apply_hook_surface_action, _trace_identity, _error_trace_payload (+6) |
| `src/slopgate/engine/_evaluation.py` | _evaluation_metadata, evaluate_payload, _extract_model_provider, _fallback_command, _extract_command (+3) |
| `tests/engine/test_08_py_quality_010_to_sed_not_safe_read.py` | _posttool, test_three_siblings_triggers, test_two_siblings_ok, test_different_prefixes_dont_combine, test_message_suggests_package_structure (+3) |
| `tests/engine/test_py_code_012_advisory_compaction.py` | write_payload, compact_generated_first_hit, test_compact_context_advisories_records_public_seam_metadata, test_compact_context_advisories_normalizes_first_hit_for_relative_paths, feature_envy_findings (+3) |
| `tests/engine/test_06_lang_graph_to_py_quality_009.py` | posttool_payload, test_lg_state_001, test_lg_node_001, test_non_graph_file_ignored, test_set_entry_point_flagged (+2) |
| `src/slopgate/engine/advisories.py` | _metadata_path, _suppress_context, _record_path_group, compact_context_advisories, _numeric_metadata (+1) |
| `tests/engine/baseline_guard_support.py` | _write_baseline, test_increase_blocked, test_relative_baseline_path_uses_payload_cwd, test_new_nonempty_baseline_creation_blocked, test_repo_wide_baseline_commands_blocked |
| `src/slopgate/engine/_render.py` | serialize_findings, merge_updated_input, collect_context, top_decision, render_output |

## Entry Points

Start here when exploring this area:

- **`evaluate_payload`** (Function) — `src/slopgate/engine/_evaluation.py:198`
- **`dedupe_findings`** (Function) — `src/slopgate/engine/_retry.py:81`
- **`filter_search_reminder_dedupe`** (Function) — `src/slopgate/engine/_retry.py:89`
- **`inject_recent_failure_context`** (Function) — `src/slopgate/engine/_retry.py:226`
- **`enforce_retry_budget`** (Function) — `src/slopgate/engine/_retry.py:303`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `evaluate_payload` | Function | `src/slopgate/engine/_evaluation.py` | 198 |
| `dedupe_findings` | Function | `src/slopgate/engine/_retry.py` | 81 |
| `filter_search_reminder_dedupe` | Function | `src/slopgate/engine/_retry.py` | 89 |
| `inject_recent_failure_context` | Function | `src/slopgate/engine/_retry.py` | 226 |
| `enforce_retry_budget` | Function | `src/slopgate/engine/_retry.py` | 303 |
| `capture_repair_plan_signal` | Function | `src/slopgate/engine/_retry.py` | 341 |
| `resolve_enforcement_mode` | Function | `src/slopgate/engine/_runner.py` | 228 |
| `compress_repeated_import_alias_examples` | Function | `src/slopgate/engine/_hints/import_aliases.py` | 16 |
| `normalize_attempt_path` | Function | `src/slopgate/engine/_retry.py` | 33 |
| `apply_loop_aware_steering` | Function | `src/slopgate/engine/_retry.py` | 189 |
| `write_slopgate` | Function | `tests/engine/support.py` | 127 |
| `write_config_from_defaults` | Function | `tests/engine/support.py` | 140 |
| `write_skip_paths_config` | Function | `tests/engine/support.py` | 185 |
| `mutate` | Function | `tests/engine/support.py` | 188 |
| `pretool_bash_payload` | Function | `tests/engine/support.py` | 296 |
| `evaluate_pretool_bash` | Function | `tests/engine/support.py` | 312 |
| `test_rule_surface_action_overrides_runtime_finding_decision` | Function | `tests/engine/test_rule_surfaces.py` | 31 |
| `test_rule_surface_events_filter_runtime_evaluation` | Function | `tests/engine/test_rule_surfaces.py` | 55 |
| `test_opencode_file_edited_reaches_post_edit_quality` | Function | `tests/test_tool_intent_enforcement.py` | 235 |
| `assert_denied_by` | Function | `tests/support.py` | 99 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Evaluate_payload → _path_lock_for` | cross_community | 7 |
| `Evaluate_payload → _locked_file` | cross_community | 7 |
| `Evaluate_payload → Make_record` | cross_community | 4 |
| `Evaluate_payload → Object_list` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 10 calls |
| Slopgate | 4 calls |
| Cli | 1 calls |
| _staging | 1 calls |
| Enrichment | 1 calls |
| Rules | 1 calls |
| Search | 1 calls |
| Util | 1 calls |

## How to Explore

1. `context({name: "evaluate_payload"})` — see callers and callees
2. `query({search_query: "engine"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
