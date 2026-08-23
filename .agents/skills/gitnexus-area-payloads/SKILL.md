---
name: gitnexus-area-payloads
description: "Skill for the Payloads area of slopgate. 101 symbols across 15 files."
---

# Payloads

101 symbols | 15 files | Cohesion: 74%

## When to Use

- Working with code in `src/`
- Understanding how find_command_has_mutation, is_mutating_shell_command, is_safe_read_shell_command work
- Modifying payloads-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/util/payloads/_shell.py` | _has_embedded_mutating_shell, _has_interpreter_write_snippet, _has_mutating_shell_command_substitution, _has_mutating_shell_verb, _has_unsafe_shell_redirection (+15) |
| `src/slopgate/util/payloads/_intent.py` | _shell_read_intent, _shell_tool_intent, _normalized_tool_name, _tool_name, is_read_only_tool_use (+12) |
| `src/slopgate/util/payloads/targets.py` | _content_from_lines, _edit_items, ctx_execute_content_target, multi_edit_content_targets, patch_candidate_paths (+9) |
| `src/slopgate/util/payloads/_properties.py` | shell_command, content_targets, intent_reason, read_only, HookPayloadProperties (+5) |
| `src/slopgate/util/payloads/_shell_content.py` | _clean_path, _echo_redirect_targets, _heredoc_content_targets, _python_heredoc_scripts, _python_inline_scripts (+5) |
| `src/slopgate/util/payloads/_shell_paths.py` | _is_shell_glob_token, _shell_option_value, append_unique_shell_path, powershell_candidate_paths, shell_redirection_paths (+2) |
| `src/slopgate/util/payloads/_basic.py` | extract_content_from_mapping, extract_path_from_mapping, first_present, is_edit_like_tool, is_shell_tool (+2) |
| `src/slopgate/util/payloads/_patches.py` | _patch_path_from_line, extract_added_patch_content, parse_patch_candidate_paths, _parse_patch_contents, _record_patch_content (+2) |
| `src/slopgate/rules/common/_shell_read.py` | _is_makefile_target_execution, _is_sed_transform, is_safe_bash_read |
| `src/slopgate/util/payloads/_shell_script_writes.py` | script_api_write_paths |

## Entry Points

Start here when exploring this area:

- **`find_command_has_mutation`** (Function) — `src/slopgate/util/payloads/_shell.py:165`
- **`is_mutating_shell_command`** (Function) — `src/slopgate/util/payloads/_shell.py:287`
- **`is_safe_read_shell_command`** (Function) — `src/slopgate/util/payloads/_shell.py:304`
- **`script_write_paths`** (Function) — `src/slopgate/util/payloads/_shell.py:322`
- **`shell_command_executable_paths`** (Function) — `src/slopgate/util/payloads/_shell.py:144`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `HookPayload` | Class | `src/slopgate/util/payloads/_payload.py` | 11 |
| `HookPayloadProperties` | Class | `src/slopgate/util/payloads/_properties.py` | 169 |
| `find_command_has_mutation` | Function | `src/slopgate/util/payloads/_shell.py` | 165 |
| `is_mutating_shell_command` | Function | `src/slopgate/util/payloads/_shell.py` | 287 |
| `is_safe_read_shell_command` | Function | `src/slopgate/util/payloads/_shell.py` | 304 |
| `script_write_paths` | Function | `src/slopgate/util/payloads/_shell.py` | 322 |
| `shell_command_executable_paths` | Function | `src/slopgate/util/payloads/_shell.py` | 144 |
| `shell_command_paths` | Function | `src/slopgate/util/payloads/_shell.py` | 333 |
| `shell_tokens` | Function | `src/slopgate/util/payloads/_shell.py` | 151 |
| `append_unique_shell_path` | Function | `src/slopgate/util/payloads/_shell_paths.py` | 42 |
| `powershell_candidate_paths` | Function | `src/slopgate/util/payloads/_shell_paths.py` | 87 |
| `shell_redirection_paths` | Function | `src/slopgate/util/payloads/_shell_paths.py` | 111 |
| `shell_token_path_candidates` | Function | `src/slopgate/util/payloads/_shell_paths.py` | 66 |
| `script_api_write_paths` | Function | `src/slopgate/util/payloads/_shell_script_writes.py` | 37 |
| `extract_content_from_mapping` | Function | `src/slopgate/util/payloads/_basic.py` | 49 |
| `extract_path_from_mapping` | Function | `src/slopgate/util/payloads/_basic.py` | 28 |
| `first_present` | Function | `src/slopgate/util/payloads/_basic.py` | 18 |
| `extract_added_patch_content` | Function | `src/slopgate/util/payloads/_patches.py` | 28 |
| `parse_patch_candidate_paths` | Function | `src/slopgate/util/payloads/_patches.py` | 19 |
| `ctx_execute_content_target` | Function | `src/slopgate/util/payloads/targets.py` | 70 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Evaluate → _carrier_text` | cross_community | 9 |
| `Evaluate → _text_from_mapping` | cross_community | 9 |
| `Evaluate → _is_leading_shell_assignment` | cross_community | 9 |
| `Evaluate → _carrier_text` | cross_community | 9 |
| `Evaluate → _text_from_mapping` | cross_community | 9 |
| `Evaluate → Object_dict` | cross_community | 9 |
| `Evaluate → Object_dict` | cross_community | 9 |
| `Evaluate → Shell_tokens` | cross_community | 8 |
| `Evaluate → _is_leading_shell_assignment` | cross_community | 8 |
| `Evaluate → _carrier_text` | cross_community | 8 |

## How to Explore

1. `context({name: "find_command_has_mutation"})` — see callers and callees
2. `query({search_query: "payloads"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
