---
name: cli
description: "Skill for the Cli area of slopgate. 167 symbols across 34 files."
---

# Cli

167 symbols | 34 files | Cohesion: 77%

## When to Use

- Working with code in `src/`
- Understanding how string_arg, cmd_migrate, config_dir work
- Modifying cli-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/cli/parsers.py` | add_dry_run_argument, _add_command_parser, _add_install_scope_arguments, _add_platform_install_parser, _add_suite_update_arguments (+11) |
| `src/slopgate/cli/commands.py` | _bool_arg, _int_arg, _project_root_arg, cmd_check, cmd_enroll (+9) |
| `src/slopgate/search/cli/init.py` | _bool_arg, _guard_overwrite, _scaffold_integration, _print_rows, _print_init_summary (+9) |
| `src/slopgate/cli/main.py` | _callable_attr, _string_list_attr, _search_subcommands, _normalize_search_argv, _normalize_isx_argv (+9) |
| `src/slopgate/cli/js_ts_tests.py` | execute_default_js_ts_tests, _group_tests_by_package_root, _nearest_package_root, is_js_ts_path, is_js_ts_test_path (+8) |
| `src/slopgate/cli/changed_tests.py` | project_root, changed_files_since, execute_selected_tests, run_changed_test_workflow, _execute_default_selected_tests (+6) |
| `src/slopgate/cli/_migrate.py` | _bool_arg, string_arg, _rewrite_toml_sections, _migrate_repo_marker, _legacy_config_dir (+3) |
| `src/slopgate/cli/parsers_lint.py` | _add_lint_analysis_parser, _add_lint_analysis_parsers, _add_lint_path_subcommand, _add_lint_path_subcommands, _add_lint_init_parser (+2) |
| `src/slopgate/cli/hook_runtime.py` | cmd_daemon, _daemon_socket_path_arg, _daemon_socket_path_for_handle, _positive_int_arg, cmd_handle (+2) |
| `src/slopgate/cli/_version_check.py` | _should_skip_check, _fetch_latest_version, _version_from_payload, _cache_from_payload, _read_cache (+2) |

## Entry Points

Start here when exploring this area:

- **`string_arg`** (Function) — `src/slopgate/cli/_migrate.py:25`
- **`cmd_migrate`** (Function) — `src/slopgate/cli/_migrate.py:120`
- **`config_dir`** (Function) — `src/slopgate/config/_discovery.py:8`
- **`detect_root`** (Function) — `src/slopgate/config/_discovery.py:75`
- **`is_windows`** (Function) — `src/slopgate/util/platform.py:11`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `string_arg` | Function | `src/slopgate/cli/_migrate.py` | 25 |
| `cmd_migrate` | Function | `src/slopgate/cli/_migrate.py` | 120 |
| `config_dir` | Function | `src/slopgate/config/_discovery.py` | 8 |
| `detect_root` | Function | `src/slopgate/config/_discovery.py` | 75 |
| `is_windows` | Function | `src/slopgate/util/platform.py` | 11 |
| `user_config_dir` | Function | `src/slopgate/util/platform.py` | 15 |
| `user_data_dir` | Function | `src/slopgate/util/platform.py` | 27 |
| `cmd_check` | Function | `src/slopgate/cli/commands.py` | 59 |
| `cmd_enroll` | Function | `src/slopgate/cli/commands.py` | 106 |
| `cmd_replay` | Function | `src/slopgate/cli/commands.py` | 129 |
| `cmd_install` | Function | `src/slopgate/cli/commands.py` | 144 |
| `cmd_uninstall` | Function | `src/slopgate/cli/commands.py` | 185 |
| `cmd_install_suite` | Function | `src/slopgate/cli/commands.py` | 214 |
| `cmd_update_suite` | Function | `src/slopgate/cli/commands.py` | 232 |
| `cmd_stats` | Function | `src/slopgate/cli/commands.py` | 247 |
| `string_arg` | Function | `src/slopgate/cli/io.py` | 40 |
| `add_install_scope_arguments` | Function | `src/slopgate/cli/_install_scope_args.py` | 11 |
| `add_dry_run_argument` | Function | `src/slopgate/cli/parsers.py` | 35 |
| `cmd_init` | Function | `src/slopgate/search/cli/init.py` | 198 |
| `expand` | Function | `src/slopgate/search/config.py` | 114 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Cmd_init → Object_dict` | cross_community | 6 |
| `Cmd_init → Object_list` | cross_community | 6 |
| `Cmd_init → String_value` | cross_community | 6 |
| `Install_codex → Is_windows` | cross_community | 5 |
| `Install_claude → Is_windows` | cross_community | 5 |
| `Install_cursor → Is_windows` | cross_community | 5 |
| `Load_config → Is_windows` | cross_community | 5 |
| `Uninstall_opencode → Is_windows` | cross_community | 5 |
| `Uninstall_autoupdate → Is_windows` | cross_community | 5 |
| `Cmd_handle → _linux_runtime_socket_path` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Search | 6 calls |
| Util | 4 calls |
| Installer | 3 calls |
| Slopgate | 2 calls |
| Suite | 1 calls |

## How to Explore

1. `context({name: "string_arg"})` — see callers and callees
2. `query({search_query: "cli"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
