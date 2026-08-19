---
name: adapters
description: "Skill for the Adapters area of slopgate. 212 symbols across 28 files."
---

# Adapters

212 symbols | 28 files | Cohesion: 69%

## When to Use

- Working with code in `tests/`
- Understanding how test_claude_team_event_blocks_do_not_render_continue_false, test_cursor_adapter_renders_pretool_deny_in_native_schema, test_cursor_adapter_renders_stop_block_as_followup work
- Modifying adapters-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/adapters/test_05_open_code_adapter_normalize_to_open_code_adapter_normalize_tool_result.py` | test_normalize_maps_event_name, test_normalize_preserves_already_canonical, test_normalize_maps_known_lowercase_tool_alias, test_normalize_preserves_unknown_lowercase_tool_name, test_normalize_session_idle_maps_to_stop (+11) |
| `src/slopgate/adapters/codex.py` | _render_codex_permission_request, _canonical_codex_event, render_output, record_metric, _apply_codex_block_decision (+11) |
| `src/slopgate/adapters/cursor_output.py` | _decision_text, _append_context, _deny_permission_output, _ask_permission_output, _allow_permission_output (+9) |
| `tests/adapters/test_03_codex_adapter_basic.py` | test_pretool_deny, test_pretool_allow_can_rewrite_input, test_stop_block, test_user_prompt_submit_block, test_unsupported_event_returns_none (+8) |
| `src/slopgate/adapters/opencode.py` | normalize_payload, render_output, record_metric, _block_output, _context_output (+6) |
| `src/slopgate/adapters/claude.py` | _render_task_or_idle, render_output, _decision_reason, _render_hook_specific_permission, _render_pre_tool_use (+6) |
| `tests/adapters/test_11_cursor_adapter_basic.py` | test_cursor_adapter_renders_pretool_deny_in_native_schema, test_cursor_adapter_renders_stop_block_as_followup, test_cursor_adapter_renders_before_submit_prompt_block, test_cursor_adapter_renders_pretool_allow_for_empty_findings, test_cursor_adapter_renders_before_submit_prompt_allow_for_empty_findings (+6) |
| `tests/adapters/test_06_open_code_adapter_render_pre_tool.py` | test_pretool_deny_action_block, test_pretool_allow_with_updated_args, test_pretool_context_only, test_pretool_ask_maps_to_block, test_no_findings_returns_none (+5) |
| `src/slopgate/adapters/cursor.py` | _first_string, _nested_tool_input, _tool_name_from_raw, _shell_tool_input, _file_tool_input (+5) |
| `tests/adapters/test_07_open_code_adapter_render_post_tool_to_base_adapter_helpers.py` | test_posttool_block, test_posttool_with_context_and_decision, test_posttool_context_only, test_stop_continue, test_stop_context_only (+4) |

## Entry Points

Start here when exploring this area:

- **`test_claude_team_event_blocks_do_not_render_continue_false`** (Function) — `tests/adapters/test_08_claude_team_event_retry_semantics.py:67`
- **`test_cursor_adapter_renders_pretool_deny_in_native_schema`** (Function) — `tests/adapters/test_11_cursor_adapter_basic.py:123`
- **`test_cursor_adapter_renders_stop_block_as_followup`** (Function) — `tests/adapters/test_11_cursor_adapter_basic.py:147`
- **`test_cursor_adapter_renders_before_submit_prompt_block`** (Function) — `tests/adapters/test_11_cursor_adapter_basic.py:163`
- **`test_cursor_adapter_renders_pretool_allow_for_empty_findings`** (Function) — `tests/adapters/test_11_cursor_adapter_basic.py:182`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `PlatformAdapter` | Class | `src/slopgate/adapters/base.py` | 86 |
| `ClaudeAdapter` | Class | `src/slopgate/adapters/claude.py` | 65 |
| `CodexAdapter` | Class | `src/slopgate/adapters/codex.py` | 232 |
| `CursorAdapter` | Class | `src/slopgate/adapters/cursor.py` | 165 |
| `OpenCodeAdapter` | Class | `src/slopgate/adapters/opencode.py` | 76 |
| `PiAdapter` | Class | `src/slopgate/adapters/pi.py` | 134 |
| `test_claude_team_event_blocks_do_not_render_continue_false` | Function | `tests/adapters/test_08_claude_team_event_retry_semantics.py` | 67 |
| `test_cursor_adapter_renders_pretool_deny_in_native_schema` | Function | `tests/adapters/test_11_cursor_adapter_basic.py` | 123 |
| `test_cursor_adapter_renders_stop_block_as_followup` | Function | `tests/adapters/test_11_cursor_adapter_basic.py` | 147 |
| `test_cursor_adapter_renders_before_submit_prompt_block` | Function | `tests/adapters/test_11_cursor_adapter_basic.py` | 163 |
| `test_cursor_adapter_renders_pretool_allow_for_empty_findings` | Function | `tests/adapters/test_11_cursor_adapter_basic.py` | 182 |
| `test_cursor_adapter_renders_before_submit_prompt_allow_for_empty_findings` | Function | `tests/adapters/test_11_cursor_adapter_basic.py` | 202 |
| `test_cursor_adapter_renders_post_tool_use_as_additional_context` | Function | `tests/adapters/test_11_cursor_adapter_basic.py` | 213 |
| `test_cursor_adapter_subagent_start_deny_omits_agent_message` | Function | `tests/adapters/test_11_cursor_adapter_basic.py` | 227 |
| `test_pi_pretool_deny_returns_block_result` | Function | `tests/adapters/test_13_pi_adapter_contract.py` | 63 |
| `require_rendered` | Function | `tests/test_adapters.py` | 63 |
| `render_cursor_output` | Function | `src/slopgate/adapters/cursor_output.py` | 168 |
| `render_permission_request_output` | Function | `src/slopgate/adapters/base.py` | 63 |
| `canonical_event_name` | Function | `src/slopgate/adapters/_payload_fields.py` | 16 |
| `merge_session_id` | Function | `src/slopgate/adapters/_payload_fields.py` | 38 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Normalize_payload → String_value` | cross_community | 5 |
| `Normalize_payload → Is_object_dict` | cross_community | 3 |
| `Normalize_payload → Object_dict` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Search | 12 calls |
| Util | 9 calls |

## How to Explore

1. `context({name: "test_claude_team_event_blocks_do_not_render_continue_false"})` — see callers and callees
2. `query({search_query: "adapters"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
