---
name: payloads
description: "Skill for the Payloads area of slopgate. 94 symbols across 10 files."
---

# Payloads

94 symbols | 10 files | Cohesion: 82%

## When to Use

- Working with code in `src/`
- Understanding how shell_command_executable_paths, shell_tokens, command_has_word work
- Modifying payloads-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/util/payloads/_shell.py` | _is_leading_shell_assignment, _shell_command_executable_indexes, shell_command_executable_paths, shell_tokens, command_has_word (+15) |
| `src/slopgate/util/payloads/_intent.py` | _shell_read_intent, _shell_tool_intent, _tool_name, _normalized_tool_name, _named_tool_intent (+13) |
| `src/slopgate/util/payloads/targets.py` | _content_from_lines, _edit_items, tool_input_path, tool_input_content_target, ctx_execute_content_target (+9) |
| `src/slopgate/util/payloads/_properties.py` | shell_command, content_targets, intent_reason, read_only, mutating (+7) |
| `src/slopgate/util/payloads/_shell_content.py` | _clean_path, _python_inline_scripts, _python_heredoc_scripts, _heredoc_content_targets, _echo_redirect_targets (+5) |
| `src/slopgate/util/payloads/_basic.py` | first_present, extract_path_from_mapping, extract_content_from_mapping, is_edit_like_tool, is_bash_tool (+3) |
| `src/slopgate/util/payloads/_shell_paths.py` | _is_shell_glob_token, append_unique_shell_path, _shell_option_value, shell_token_path_candidates, powershell_candidate_paths (+2) |
| `src/slopgate/util/payloads/_patches.py` | _patch_path_from_line, parse_patch_candidate_paths, extract_added_patch_content |
| `src/slopgate/util/payloads/_shell_script_writes.py` | script_api_write_paths |
| `src/slopgate/util/payloads/_payload.py` | HookPayload |

## Entry Points

Start here when exploring this area:

- **`shell_command_executable_paths`** (Function) — `src/slopgate/util/payloads/_shell.py:144`
- **`shell_tokens`** (Function) — `src/slopgate/util/payloads/_shell.py:151`
- **`command_has_word`** (Function) — `src/slopgate/util/payloads/_shell.py:158`
- **`find_command_has_mutation`** (Function) — `src/slopgate/util/payloads/_shell.py:165`
- **`is_mutating_shell_command`** (Function) — `src/slopgate/util/payloads/_shell.py:287`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `HookPayload` | Class | `src/slopgate/util/payloads/_payload.py` | 11 |
| `HookPayloadProperties` | Class | `src/slopgate/util/payloads/_properties.py` | 169 |
| `shell_command_executable_paths` | Function | `src/slopgate/util/payloads/_shell.py` | 144 |
| `shell_tokens` | Function | `src/slopgate/util/payloads/_shell.py` | 151 |
| `command_has_word` | Function | `src/slopgate/util/payloads/_shell.py` | 158 |
| `find_command_has_mutation` | Function | `src/slopgate/util/payloads/_shell.py` | 165 |
| `is_mutating_shell_command` | Function | `src/slopgate/util/payloads/_shell.py` | 287 |
| `is_safe_read_shell_command` | Function | `src/slopgate/util/payloads/_shell.py` | 304 |
| `first_present` | Function | `src/slopgate/util/payloads/_basic.py` | 17 |
| `extract_path_from_mapping` | Function | `src/slopgate/util/payloads/_basic.py` | 27 |
| `extract_content_from_mapping` | Function | `src/slopgate/util/payloads/_basic.py` | 48 |
| `parse_patch_candidate_paths` | Function | `src/slopgate/util/payloads/_patches.py` | 19 |
| `extract_added_patch_content` | Function | `src/slopgate/util/payloads/_patches.py` | 28 |
| `tool_input_path` | Function | `src/slopgate/util/payloads/targets.py` | 50 |
| `tool_input_content_target` | Function | `src/slopgate/util/payloads/targets.py` | 57 |
| `ctx_execute_content_target` | Function | `src/slopgate/util/payloads/targets.py` | 66 |
| `multi_edit_content_targets` | Function | `src/slopgate/util/payloads/targets.py` | 83 |
| `patch_content_targets` | Function | `src/slopgate/util/payloads/targets.py` | 108 |
| `unique_content_targets` | Function | `src/slopgate/util/payloads/targets.py` | 119 |
| `patch_candidate_paths` | Function | `src/slopgate/util/payloads/targets.py` | 149 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Content_targets → First_present` | intra_community | 4 |
| `Content_targets → Object_list` | cross_community | 4 |
| `Candidate_path_source → Object_dict` | cross_community | 4 |
| `Candidate_path_source → _has_unsafe_shell_redirection` | cross_community | 4 |
| `Candidate_path_source → Find_command_has_mutation` | cross_community | 4 |
| `Candidate_path_source → Shell_tokens` | cross_community | 4 |
| `Candidate_path_source → _shell_script_argument_indexes` | cross_community | 4 |
| `Candidate_path_source → _is_shell_glob_token` | cross_community | 4 |
| `Candidate_path_source → _is_leading_shell_assignment` | cross_community | 4 |
| `Candidate_paths → First_present` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Util | 7 calls |
| Search | 2 calls |

## How to Explore

1. `context({name: "shell_command_executable_paths"})` — see callers and callees
2. `query({search_query: "payloads"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
