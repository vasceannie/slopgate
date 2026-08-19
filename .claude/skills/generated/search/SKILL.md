---
name: search
description: "Skill for the Search area of slopgate. 65 symbols across 13 files."
---

# Search

65 symbols | 13 files | Cohesion: 77%

## When to Use

- Working with code in `src/`
- Understanding how object_list, string_value, string_arg work
- Modifying search-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/search/cli/__init__.py` | string_arg, _bool_arg, _string_list_arg, _token_from_cli, _token_from_config (+13) |
| `src/slopgate/search/runtime.py` | fetch_models, embedding_like, _apply_base_url, _apply_api_key, _first_matching_git_token (+9) |
| `src/slopgate/search/index_ops.py` | _read_index_metadata, local_indexes, find_local_index, _resolve_current_repo_target, _resolve_index_name (+2) |
| `src/slopgate/search/git_utils.py` | _host_path_from_match, normalize_clone_url, urls_match, get_git_remote_url, get_git_repo_root (+1) |
| `src/slopgate/search/scaffolds.py` | write_text_file, append_unique_json_list, render_isx_skill, scaffold_skill, scaffold_opencode_plugin |
| `src/slopgate/search/cli/doctor.py` | _print_rows, _print_doctor_config, _probe_doctor_endpoint, cmd_doctor |
| `src/slopgate/search/config.py` | _coerce_search_config, load_config, save_config |
| `src/slopgate/_types.py` | object_list, string_value |
| `src/slopgate/adapters/pi.py` | _raw_event_name, _sync_user_bash_command |
| `src/slopgate/search/completions.py` | print_completion |

## Entry Points

Start here when exploring this area:

- **`object_list`** (Function) — `src/slopgate/_types.py:27`
- **`string_value`** (Function) — `src/slopgate/_types.py:34`
- **`string_arg`** (Function) — `src/slopgate/search/cli/__init__.py:28`
- **`cmd_models`** (Function) — `src/slopgate/search/cli/__init__.py:134`
- **`cmd_use`** (Function) — `src/slopgate/search/cli/__init__.py:154`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `object_list` | Function | `src/slopgate/_types.py` | 27 |
| `string_value` | Function | `src/slopgate/_types.py` | 34 |
| `string_arg` | Function | `src/slopgate/search/cli/__init__.py` | 28 |
| `cmd_models` | Function | `src/slopgate/search/cli/__init__.py` | 134 |
| `cmd_use` | Function | `src/slopgate/search/cli/__init__.py` | 154 |
| `cmd_list` | Function | `src/slopgate/search/cli/__init__.py` | 177 |
| `cmd_add` | Function | `src/slopgate/search/cli/__init__.py` | 208 |
| `cmd_search` | Function | `src/slopgate/search/cli/__init__.py` | 215 |
| `cmd_remove` | Function | `src/slopgate/search/cli/__init__.py` | 224 |
| `cmd_sync` | Function | `src/slopgate/search/cli/__init__.py` | 241 |
| `cmd_reindex` | Function | `src/slopgate/search/cli/__init__.py` | 247 |
| `cmd_completions` | Function | `src/slopgate/search/cli/__init__.py` | 267 |
| `cmd_doctor` | Function | `src/slopgate/search/cli/doctor.py` | 72 |
| `print_completion` | Function | `src/slopgate/search/completions.py` | 127 |
| `load_config` | Function | `src/slopgate/search/config.py` | 126 |
| `normalize_clone_url` | Function | `src/slopgate/search/git_utils.py` | 20 |
| `urls_match` | Function | `src/slopgate/search/git_utils.py` | 45 |
| `get_git_remote_url` | Function | `src/slopgate/search/git_utils.py` | 52 |
| `get_git_repo_root` | Function | `src/slopgate/search/git_utils.py` | 69 |
| `resolve_add_repo` | Function | `src/slopgate/search/git_utils.py` | 88 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Cmd_init → Object_dict` | cross_community | 6 |
| `Cmd_init → Object_list` | cross_community | 6 |
| `Cmd_init → String_value` | cross_community | 6 |
| `Serve → String_value` | cross_community | 6 |
| `Cmd_add → String_value` | intra_community | 6 |
| `Normalize_payload → String_value` | cross_community | 5 |
| `Cmd_use → String_value` | intra_community | 5 |
| `Cmd_use → _first_matching_git_token` | intra_community | 5 |
| `Cmd_remove → Object_dict` | cross_community | 5 |
| `Cmd_remove → _host_path_from_match` | intra_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Util | 9 calls |
| Cli | 2 calls |
| State | 1 calls |

## How to Explore

1. `context({name: "object_list"})` — see callers and callees
2. `query({search_query: "search"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
