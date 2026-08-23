---
name: gitnexus-area-installer
description: "Skill for the Installer area of slopgate. 107 symbols across 16 files."
---

# Installer

107 symbols | 16 files | Cohesion: 77%

## When to Use

- Working with code in `src/`
- Understanding how install_claude, uninstall_claude, install_codex work
- Modifying installer-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/installer/_pi.py` | _pi_contained_root, _pi_user_root, install_pi, pi_project_extension_path, pi_user_extension_path (+14) |
| `src/slopgate/installer/_codex.py` | _codex_contained_root, _codex_project_hooks_path, _codex_user_hooks_path, _codex_user_root, install_codex (+11) |
| `src/slopgate/installer/_cursor.py` | _cursor_contained_root, _cursor_user_root, cursor_project_hooks_path, cursor_user_hooks_path, install_cursor (+7) |
| `src/slopgate/installer/_opencode.py` | _opencode_project_plugin_path, _uninstall_opencode_at, uninstall_opencode, _opencode_install_content, _warn_stale_opencode_identity (+6) |
| `src/slopgate/installer/_claude.py` | _claude_contained_root, _claude_project_settings_path, _claude_user_root, _claude_user_settings_path, _install_claude_at (+5) |
| `src/slopgate/installer/_suite.py` | _package_update_command, _sync_autoupdate_facade_dependencies, build_scheduler_plan, current_device_label, discover_install_sites (+5) |
| `src/slopgate/installer/opencode_identity.py` | _canonical_version, _dependency_version, _json_file, _opencode_identity_status, _opencode_lock_version (+1) |
| `src/slopgate/installer/_install_scope.py` | normalize_install_scope, resolve_project_root, resolve_scoped_install_paths, scope_paths, warn_residual_install_scope |
| `src/slopgate/installer/_shared/hooks.py` | load_existing_json_object, prepare_owned_hooks_document, require_json_object |
| `src/slopgate/installer/_shared/writes.py` | remove_file_with_backup, uninstall_hooks_file, print_binary_install_summary |

## Entry Points

Start here when exploring this area:

- **`install_claude`** (Function) — `src/slopgate/installer/_claude.py:131`
- **`uninstall_claude`** (Function) — `src/slopgate/installer/_claude.py:196`
- **`install_codex`** (Function) — `src/slopgate/installer/_codex.py:260`
- **`uninstall_codex`** (Function) — `src/slopgate/installer/_codex.py:303`
- **`cursor_project_hooks_path`** (Function) — `src/slopgate/installer/_cursor.py:62`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `install_claude` | Function | `src/slopgate/installer/_claude.py` | 131 |
| `uninstall_claude` | Function | `src/slopgate/installer/_claude.py` | 196 |
| `install_codex` | Function | `src/slopgate/installer/_codex.py` | 260 |
| `uninstall_codex` | Function | `src/slopgate/installer/_codex.py` | 303 |
| `cursor_project_hooks_path` | Function | `src/slopgate/installer/_cursor.py` | 62 |
| `cursor_user_hooks_path` | Function | `src/slopgate/installer/_cursor.py` | 58 |
| `install_cursor` | Function | `src/slopgate/installer/_cursor.py` | 177 |
| `uninstall_cursor` | Function | `src/slopgate/installer/_cursor.py` | 214 |
| `normalize_install_scope` | Function | `src/slopgate/installer/_install_scope.py` | 45 |
| `resolve_project_root` | Function | `src/slopgate/installer/_install_scope.py` | 54 |
| `resolve_scoped_install_paths` | Function | `src/slopgate/installer/_install_scope.py` | 77 |
| `scope_paths` | Function | `src/slopgate/installer/_install_scope.py` | 63 |
| `warn_residual_install_scope` | Function | `src/slopgate/installer/_install_scope.py` | 145 |
| `uninstall_opencode` | Function | `src/slopgate/installer/_opencode.py` | 269 |
| `install_pi` | Function | `src/slopgate/installer/_pi.py` | 262 |
| `pi_project_extension_path` | Function | `src/slopgate/installer/_pi.py` | 82 |
| `pi_user_extension_path` | Function | `src/slopgate/installer/_pi.py` | 71 |
| `uninstall_pi` | Function | `src/slopgate/installer/_pi.py` | 321 |
| `load_existing_json_object` | Function | `src/slopgate/installer/_shared/hooks.py` | 180 |
| `prepare_owned_hooks_document` | Function | `src/slopgate/installer/_shared/hooks.py` | 189 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Install_suite → _binary_is_runnable` | cross_community | 8 |
| `Uninstall_suite → _binary_is_runnable` | cross_community | 8 |
| `Install_suite → Base_invocation` | cross_community | 7 |
| `Uninstall_suite → Base_invocation` | cross_community | 7 |
| `Install_suite → Is_windows` | cross_community | 7 |
| `Uninstall_suite → Is_windows` | cross_community | 7 |
| `Main → Is_windows` | cross_community | 6 |
| `Install_claude → Is_windows` | cross_community | 6 |
| `Install_codex → Is_windows` | cross_community | 6 |
| `Install_cursor → Is_windows` | cross_community | 6 |

## How to Explore

1. `context({name: "install_claude"})` — see callers and callees
2. `query({search_query: "installer"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
