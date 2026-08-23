---
name: gitnexus-area-cli
description: "Skill for the Cli area of slopgate. 195 symbols across 42 files."
---

# Cli

195 symbols | 42 files | Cohesion: 76%

## When to Use

- Working with code in `src/`
- Understanding how cmd_add, cmd_completions, cmd_list work
- Modifying cli-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/search/cli/__init__.py` | _bool_arg, _build_add_args, _embed_token_in_url, _resolve_token, _run_add_repository (+14) |
| `src/slopgate/cli/parsers.py` | _add_config_parsers, add_details_argument, add_optional_path_argument, build_parser, _add_command_parser (+11) |
| `src/slopgate/search/cli/init.py` | _print_discovered, _bool_arg, _guard_overwrite, _print_init_summary, _print_next_steps (+9) |
| `src/slopgate/cli/main.py` | _bool_attr, _normalize_isx_argv, _normalize_search_argv, _search_subcommands, _string_attr (+9) |
| `src/slopgate/cli/js_ts_tests.py` | _git_submodule_roots, _group_tests_by_package_root, _nearest_package_root, _parent_recorded_submodule_ref, _prefixed_submodule_changes (+8) |
| `src/slopgate/cli/commands.py` | cmd_version, _string_tuple_arg, cmd_test, _bool_arg, _int_arg (+6) |
| `src/slopgate/cli/changed_tests.py` | _execute_default_selected_tests, changed_files_since, execute_selected_tests, normalize_changed_files, project_root (+4) |
| `src/slopgate/search/runtime.py` | choose_litellm_model, current_islands_config_path, embedding_like, fetch_models, fetch_runtime_models (+2) |
| `src/slopgate/cli/parsers_lint.py` | _add_lint_analysis_parser, _add_lint_analysis_parsers, _add_lint_init_parser, _add_lint_path_subcommand, _add_lint_path_subcommands (+2) |
| `src/slopgate/cli/hook_runtime.py` | _daemon_socket_path_arg, _daemon_socket_path_for_handle, _positive_int_arg, cmd_daemon, _try_handle_via_daemon (+2) |

## Entry Points

Start here when exploring this area:

- **`cmd_add`** (Function) — `src/slopgate/search/cli/__init__.py:208`
- **`cmd_completions`** (Function) — `src/slopgate/search/cli/__init__.py:267`
- **`cmd_list`** (Function) — `src/slopgate/search/cli/__init__.py:177`
- **`cmd_models`** (Function) — `src/slopgate/search/cli/__init__.py:134`
- **`cmd_reindex`** (Function) — `src/slopgate/search/cli/__init__.py:247`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `cmd_add` | Function | `src/slopgate/search/cli/__init__.py` | 208 |
| `cmd_completions` | Function | `src/slopgate/search/cli/__init__.py` | 267 |
| `cmd_list` | Function | `src/slopgate/search/cli/__init__.py` | 177 |
| `cmd_models` | Function | `src/slopgate/search/cli/__init__.py` | 134 |
| `cmd_reindex` | Function | `src/slopgate/search/cli/__init__.py` | 247 |
| `cmd_remove` | Function | `src/slopgate/search/cli/__init__.py` | 224 |
| `cmd_search` | Function | `src/slopgate/search/cli/__init__.py` | 215 |
| `cmd_sync` | Function | `src/slopgate/search/cli/__init__.py` | 241 |
| `cmd_use` | Function | `src/slopgate/search/cli/__init__.py` | 154 |
| `string_arg` | Function | `src/slopgate/search/cli/__init__.py` | 28 |
| `cmd_doctor` | Function | `src/slopgate/search/cli/doctor.py` | 72 |
| `print_completion` | Function | `src/slopgate/search/completions.py` | 127 |
| `load_config` | Function | `src/slopgate/search/config.py` | 127 |
| `choose_litellm_model` | Function | `src/slopgate/search/runtime.py` | 59 |
| `current_islands_config_path` | Function | `src/slopgate/search/runtime.py` | 196 |
| `embedding_like` | Function | `src/slopgate/search/runtime.py` | 47 |
| `fetch_models` | Function | `src/slopgate/search/runtime.py` | 26 |
| `fetch_runtime_models` | Function | `src/slopgate/search/runtime.py` | 210 |
| `islands_binary` | Function | `src/slopgate/search/runtime.py` | 187 |
| `run_islands` | Function | `src/slopgate/search/runtime.py` | 219 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Select_tests_for_changed_files → Object_dict` | cross_community | 10 |
| `Cmd_stats → Object_list` | cross_community | 10 |
| `Evaluate_hook_request → _locked_file` | cross_community | 9 |
| `Evaluate_hook_request → _path_lock_for` | cross_community | 9 |
| `Cmd_stats → Is_third_party_or_virtualenv_path` | cross_community | 9 |
| `Select_tests_for_changed_files → _coerce_path_entries` | cross_community | 8 |
| `Select_tests_for_changed_files → _resolve_path_entries` | cross_community | 8 |
| `Cmd_daemon → _session_index_context` | cross_community | 8 |
| `Cmd_daemon → _marker_signature` | cross_community | 8 |
| `Cmd_daemon → _encode_frame` | cross_community | 8 |

## How to Explore

1. `context({name: "cmd_add"})` — see callers and callees
2. `query({search_query: "cli"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
