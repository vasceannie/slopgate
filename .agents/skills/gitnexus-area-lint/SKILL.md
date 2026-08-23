---
name: gitnexus-area-lint
description: "Skill for the Lint area of slopgate. 154 symbols across 33 files."
---

# Lint

154 symbols | 33 files | Cohesion: 79%

## When to Use

- Working with code in `src/`
- Understanding how format_update_notice, build_selection_index, discover_project_root work
- Modifying lint-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/cli/lint/report.py` | _coerce_baseline_inputs, _print_scan_roots, print_collector_results, print_lint_header, _print_detailed_violations (+11) |
| `src/slopgate/cli/lint/git_base_debt.py` | _attach_profile, _collector_ids_by_rule, _git_base_debt_cache_path, _git_base_debt_detector_signature, _git_worktree_clean (+10) |
| `src/slopgate/lint/_updater.py` | _apply_injections, _build_injection_plan, _find_section_ranges, _parse_existing, _render_keys (+9) |
| `src/slopgate/lint/_toml_overrides.py` | _coerce_path_entries, _paths_section, _resolve_path_entries, apply_paths_overrides, resolve_baseline_path (+8) |
| `src/slopgate/lint/config_values.py` | _allowlist_values, _deprecated_patterns, _exception_values, _logging_values, _path_values (+5) |
| `src/slopgate/lint/_baseline.py` | assert_no_new_violations, baseline_path, load_baseline, save_baseline, save_baseline_ids (+4) |
| `src/slopgate/lint/catalog.py` | _collector_events, _collector_surfaces, _reverse_counterparts, collector_catalog, collector_ids_for_surface (+4) |
| `src/slopgate/cli/lint/commands.py` | _configured_lint_files, _lint_scan, discover_project_root, lint_freeze, lint_test_integrity (+3) |
| `src/slopgate/cli/lint/__init__.py` | _details_enabled, _path_command_name, _requested_root, _run_path_command, _run_scan_command (+3) |
| `src/slopgate/cli/repair.py` | _collector_ids_for_rules, _filter_scoped_results, _locate_repair_path, _project_lint_files, _resolve_repair_files (+1) |

## Entry Points

Start here when exploring this area:

- **`format_update_notice`** (Function) — `src/slopgate/cli/_version_check.py:134`
- **`build_selection_index`** (Function) — `src/slopgate/cli/changed_tests.py:121`
- **`discover_project_root`** (Function) — `src/slopgate/cli/lint/commands.py:20`
- **`lint_freeze`** (Function) — `src/slopgate/cli/lint/commands.py:112`
- **`lint_test_integrity`** (Function) — `src/slopgate/cli/lint/commands.py:146`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `format_update_notice` | Function | `src/slopgate/cli/_version_check.py` | 134 |
| `build_selection_index` | Function | `src/slopgate/cli/changed_tests.py` | 121 |
| `discover_project_root` | Function | `src/slopgate/cli/lint/commands.py` | 20 |
| `lint_freeze` | Function | `src/slopgate/cli/lint/commands.py` | 112 |
| `lint_test_integrity` | Function | `src/slopgate/cli/lint/commands.py` | 146 |
| `print_collector_results` | Function | `src/slopgate/cli/lint/report.py` | 296 |
| `print_lint_header` | Function | `src/slopgate/cli/lint/report.py` | 214 |
| `assert_no_new_violations` | Function | `src/slopgate/lint/_baseline.py` | 200 |
| `baseline_path` | Function | `src/slopgate/lint/_baseline.py` | 27 |
| `load_baseline` | Function | `src/slopgate/lint/_baseline.py` | 72 |
| `save_baseline` | Function | `src/slopgate/lint/_baseline.py` | 112 |
| `save_baseline_ids` | Function | `src/slopgate/lint/_baseline.py` | 96 |
| `collector_options_from_env` | Function | `src/slopgate/lint/_collector_groups/run_options.py` | 27 |
| `run_all_collectors` | Function | `src/slopgate/lint/_collector_groups/runners.py` | 77 |
| `run_test_integrity_collectors` | Function | `src/slopgate/lint/_collector_groups/runners.py` | 43 |
| `reset_quality_scope` | Function | `src/slopgate/lint/_config.py` | 191 |
| `set_config` | Function | `src/slopgate/lint/_config.py` | 169 |
| `set_quality_scope` | Function | `src/slopgate/lint/_config.py` | 183 |
| `resolve_test_file_paths` | Function | `src/slopgate/lint/_detectors/test_smells/_basic_detection.py` | 59 |
| `find_all_python_files` | Function | `src/slopgate/lint/_helpers/discovery.py` | 112 |

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

1. `context({name: "format_update_notice"})` — see callers and callees
2. `query({search_query: "lint"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
