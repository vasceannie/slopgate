---
name: lint
description: "Skill for the Lint area of slopgate. 125 symbols across 18 files."
---

# Lint

125 symbols | 18 files | Cohesion: 81%

## When to Use

- Working with code in `src/`
- Understanding how tally_rule, print_lint_summary, print_collector_results work
- Modifying lint-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/cli/lint/report.py` | _coerce_baseline_inputs, _rule_counts, _rule_status, _rule_count_text, _print_new_violations (+11) |
| `src/slopgate/lint/_updater.py` | loads, _render_keys, diff_config, _find_section_ranges, _parse_existing (+9) |
| `src/slopgate/lint/_toml_overrides.py` | _bool_map, _global_enabled_cli_rules, _repo_enabled_cli_rules, _surface_cli_rules, _global_surface_cli_rules (+8) |
| `src/slopgate/cli/lint/git_base_debt.py` | _run_git, _stripped_output, _candidate_base_refs, _is_current_branch_ref, _discover_git_base (+8) |
| `src/slopgate/lint/config_values.py` | _deprecated_patterns, _path_values, _threshold_values, _allowlist_values, _logging_values (+5) |
| `src/slopgate/lint/_baseline.py` | baseline_path, load_baseline, save_baseline_ids, save_baseline, assert_no_new_violations (+4) |
| `src/slopgate/cli/lint/commands.py` | lint_freeze, lint_test_integrity, lint_update, discover_project_root, _configured_lint_files (+3) |
| `src/slopgate/cli/lint/__init__.py` | _details_enabled, _requested_root, _scan_command_name, _path_command_name, _run_scan_command (+3) |
| `src/slopgate/lint/project_index.py` | build_project_index, _index_root, _common_parent, _sorted_project_paths, _summarize_project_file (+3) |
| `src/slopgate/lint/catalog.py` | _reverse_counterparts, _collector_surfaces, _collector_events, collector_catalog, collector_ids_for_surface (+2) |

## Entry Points

Start here when exploring this area:

- **`tally_rule`** (Function) — `src/slopgate/cli/lint/report.py:157`
- **`print_lint_summary`** (Function) — `src/slopgate/cli/lint/report.py:171`
- **`print_collector_results`** (Function) — `src/slopgate/cli/lint/report.py:296`
- **`colorize`** (Function) — `src/slopgate/cli/lint/report_format.py:9`
- **`existing_location_lines`** (Function) — `src/slopgate/cli/lint/report_format.py:13`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `tally_rule` | Function | `src/slopgate/cli/lint/report.py` | 157 |
| `print_lint_summary` | Function | `src/slopgate/cli/lint/report.py` | 171 |
| `print_collector_results` | Function | `src/slopgate/cli/lint/report.py` | 296 |
| `colorize` | Function | `src/slopgate/cli/lint/report_format.py` | 9 |
| `existing_location_lines` | Function | `src/slopgate/cli/lint/report_format.py` | 13 |
| `resolve_config_path` | Function | `src/slopgate/config/_discovery.py` | 28 |
| `load_json` | Function | `src/slopgate/config/_io.py` | 38 |
| `classified_collector_keys` | Function | `src/slopgate/lint/_parity.py` | 231 |
| `classified_hook_rule_ids` | Function | `src/slopgate/lint/_parity.py` | 236 |
| `apply_rule_enablement_overrides` | Function | `src/slopgate/lint/_toml_overrides.py` | 138 |
| `format_update_notice` | Function | `src/slopgate/cli/_version_check.py` | 134 |
| `lint_freeze` | Function | `src/slopgate/cli/lint/commands.py` | 112 |
| `lint_test_integrity` | Function | `src/slopgate/cli/lint/commands.py` | 146 |
| `print_lint_header` | Function | `src/slopgate/cli/lint/report.py` | 214 |
| `baseline_path` | Function | `src/slopgate/lint/_baseline.py` | 27 |
| `load_baseline` | Function | `src/slopgate/lint/_baseline.py` | 72 |
| `save_baseline_ids` | Function | `src/slopgate/lint/_baseline.py` | 96 |
| `save_baseline` | Function | `src/slopgate/lint/_baseline.py` | 112 |
| `assert_no_new_violations` | Function | `src/slopgate/lint/_baseline.py` | 200 |
| `build_default_values` | Function | `src/slopgate/lint/config_values.py` | 144 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Detect_semantic_clones → Object_dict` | cross_community | 7 |
| `Detect_semantic_clones → _coerce_path_entries` | cross_community | 6 |
| `Detect_semantic_clones → _resolve_path_entries` | cross_community | 6 |
| `Enroll_repo → _toml_list_of_lists` | cross_community | 6 |
| `Ast_src_collectors → _path_values` | cross_community | 6 |
| `Ast_src_collectors → _threshold_values` | cross_community | 6 |
| `Run_test_integrity_collectors → _path_values` | cross_community | 6 |
| `Run_test_integrity_collectors → _threshold_values` | cross_community | 6 |
| `Run_test_integrity_collectors → _allowlist_values` | cross_community | 6 |
| `Run_test_integrity_collectors → _logging_values` | cross_community | 6 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Config | 7 calls |
| Util | 3 calls |
| Cli | 3 calls |
| Rules | 2 calls |
| _detectors | 1 calls |
| Daemon | 1 calls |

## How to Explore

1. `context({name: "tally_rule"})` — see callers and callees
2. `query({search_query: "lint"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
