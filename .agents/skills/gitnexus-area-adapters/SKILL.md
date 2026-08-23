---
name: gitnexus-area-adapters
description: "Skill for the Adapters area of slopgate. 222 symbols across 30 files."
---

# Adapters

222 symbols | 30 files | Cohesion: 70%

## When to Use

- Working with code in `tests/`
- Understanding how test_opencode_advisory_events_have_no_blocking_render_surface, test_opencode_file_edited_contract_synthesizes_write_tool, test_opencode_harness_events_match_adapter_normalization_contract work
- Modifying adapters-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/adapters/test_05_open_code_adapter_normalize_to_open_code_adapter_normalize_tool_result.py` | test_normalize_adds_nested_native_opencode_identity_metadata, test_normalize_ignores_unrelated_top_level_event_id, test_normalize_does_not_mutate_original, test_normalize_empty_tool_name_stays_empty, test_normalize_file_edited_is_mutating (+11) |
| `src/slopgate/adapters/codex.py` | _add_codex_pretool_context_and_rewrite, _apply_codex_block_decision, _codex_decision_payload, _critical_codex_posttool_blocks, _render_codex_lifecycle_context (+11) |
| `src/slopgate/adapters/cursor_output.py` | _allow_permission_output, _append_context, _ask_permission_output, _contextual_message, _decision_text (+9) |
| `tests/adapters/test_03_codex_adapter_basic.py` | test_no_findings_returns_none, test_pretool_allow_can_rewrite_input, test_pretool_deny, test_session_start_context, test_stop_block (+8) |
| `tests/adapters/test_11_cursor_adapter_basic.py` | test_cursor_adapter_renders_before_submit_prompt_allow_for_empty_findings, test_cursor_adapter_renders_before_submit_prompt_block, test_cursor_adapter_renders_post_tool_use_as_additional_context, test_cursor_adapter_renders_pretool_allow_for_empty_findings, test_cursor_adapter_renders_pretool_deny_in_native_schema (+6) |
| `src/slopgate/adapters/claude.py` | _render_task_or_idle, render_output, _render_prompt_or_posttool, _decision_reason, _render_hook_specific_permission (+6) |
| `src/slopgate/adapters/opencode.py` | normalize_payload, _block_output, _context_output, _render_permission_request, _render_post_tool_use (+5) |
| `tests/adapters/test_06_open_code_adapter_render_pre_tool.py` | test_no_findings_returns_none, test_permission_allow_no_updated_input_returns_none, test_permission_block_maps_to_block, test_permission_deny, test_pretool_allow_with_updated_args (+5) |
| `src/slopgate/adapters/cursor.py` | _first_string, _tool_name_from_raw, _workspace_cwd, normalize_payload, CursorAdapter (+5) |
| `tests/adapters/test_07_open_code_adapter_render_post_tool_to_base_adapter_helpers.py` | test_posttool_block, test_posttool_context_only, test_session_start_context, test_stop_context_only, test_stop_continue (+4) |

## Entry Points

Start here when exploring this area:

- **`test_opencode_advisory_events_have_no_blocking_render_surface`** (Function) — `tests/adapters/test_12_opencode_adapter_harness_contract.py:158`
- **`test_opencode_file_edited_contract_synthesizes_write_tool`** (Function) — `tests/adapters/test_12_opencode_adapter_harness_contract.py:109`
- **`test_opencode_harness_events_match_adapter_normalization_contract`** (Function) — `tests/adapters/test_12_opencode_adapter_harness_contract.py:91`
- **`test_opencode_harness_events_render_expected_surface_shape`** (Function) — `tests/adapters/test_12_opencode_adapter_harness_contract.py:144`
- **`test_opencode_identity_contract_preserves_native_ids_and_worktree_scope`** (Function) — `tests/adapters/test_12_opencode_adapter_harness_contract.py:125`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `PlatformAdapter` | Class | `src/slopgate/adapters/base.py` | 86 |
| `ClaudeAdapter` | Class | `src/slopgate/adapters/claude.py` | 65 |
| `CodexAdapter` | Class | `src/slopgate/adapters/codex.py` | 232 |
| `CursorAdapter` | Class | `src/slopgate/adapters/cursor.py` | 165 |
| `OpenCodeAdapter` | Class | `src/slopgate/adapters/opencode.py` | 82 |
| `PiAdapter` | Class | `src/slopgate/adapters/pi.py` | 134 |
| `test_opencode_advisory_events_have_no_blocking_render_surface` | Function | `tests/adapters/test_12_opencode_adapter_harness_contract.py` | 158 |
| `test_opencode_file_edited_contract_synthesizes_write_tool` | Function | `tests/adapters/test_12_opencode_adapter_harness_contract.py` | 109 |
| `test_opencode_harness_events_match_adapter_normalization_contract` | Function | `tests/adapters/test_12_opencode_adapter_harness_contract.py` | 91 |
| `test_opencode_harness_events_render_expected_surface_shape` | Function | `tests/adapters/test_12_opencode_adapter_harness_contract.py` | 144 |
| `test_opencode_identity_contract_preserves_native_ids_and_worktree_scope` | Function | `tests/adapters/test_12_opencode_adapter_harness_contract.py` | 125 |
| `test_cursor_adapter_renders_before_submit_prompt_allow_for_empty_findings` | Function | `tests/adapters/test_11_cursor_adapter_basic.py` | 202 |
| `test_cursor_adapter_renders_before_submit_prompt_block` | Function | `tests/adapters/test_11_cursor_adapter_basic.py` | 163 |
| `test_cursor_adapter_renders_post_tool_use_as_additional_context` | Function | `tests/adapters/test_11_cursor_adapter_basic.py` | 213 |
| `test_cursor_adapter_renders_pretool_allow_for_empty_findings` | Function | `tests/adapters/test_11_cursor_adapter_basic.py` | 182 |
| `test_cursor_adapter_renders_pretool_deny_in_native_schema` | Function | `tests/adapters/test_11_cursor_adapter_basic.py` | 123 |
| `test_cursor_adapter_renders_stop_block_as_followup` | Function | `tests/adapters/test_11_cursor_adapter_basic.py` | 147 |
| `test_cursor_adapter_subagent_start_deny_omits_agent_message` | Function | `tests/adapters/test_11_cursor_adapter_basic.py` | 227 |
| `require_rendered` | Function | `tests/test_adapters.py` | 63 |
| `test_claude_team_event_blocks_do_not_render_continue_false` | Function | `tests/adapters/test_08_claude_team_event_retry_semantics.py` | 67 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Normalize_payload → String_value` | cross_community | 4 |

## How to Explore

1. `context({name: "test_opencode_advisory_events_have_no_blocking_render_surface"})` — see callers and callees
2. `query({search_query: "adapters"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
