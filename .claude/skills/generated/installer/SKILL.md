---
name: installer
description: "Skill for the Installer area of slopgate. 114 symbols across 13 files."
---

# Installer

114 symbols | 13 files | Cohesion: 78%

## When to Use

- Working with code in `src/`
- Understanding how install_claude, uninstall_claude, uninstall_codex work
- Modifying installer-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/installer/_pi.py` | pi_user_extension_path, pi_project_extension_path, _pi_template_text, install_pi, uninstall_pi (+18) |
| `src/slopgate/installer/_shared.py` | require_json_object, write_json_with_backup, uninstall_hooks_file, print_binary_install_summary, _command_basename (+18) |
| `src/slopgate/installer/_codex.py` | uninstall_codex, codex_hooks_block, _feature_section_bounds, _find_codex_feature_flags, _write_codex_toml_lines (+10) |
| `src/slopgate/installer/_cursor.py` | cursor_user_hooks_path, cursor_project_hooks_path, _install_cursor_at, install_cursor, uninstall_cursor (+5) |
| `src/slopgate/installer/_suite.py` | current_device_label, discover_install_sites, _package_update_command, _sync_autoupdate_facade_dependencies, build_scheduler_plan (+5) |
| `src/slopgate/installer/_opencode.py` | _opencode_config_dir, opencode_user_plugin_path, _opencode_project_plugin_path, _is_owned_opencode_plugin, _backup_and_report (+4) |
| `src/slopgate/installer/_claude.py` | _claude_user_settings_path, _claude_project_settings_path, _write_claude_settings, _install_claude_at, install_claude (+3) |
| `src/slopgate/installer/_install_scope.py` | normalize_install_scope, resolve_project_root, scope_paths, resolve_scoped_install_paths, warn_residual_install_scope (+2) |
| `src/slopgate/installer/__init__.py` | _resolved_project_root, install_platform, uninstall_platform |
| `src/slopgate/installer/hook_proxy.py` | posix_daemon_proxy_command, _posix_daemon_proxy_script |

## Entry Points

Start here when exploring this area:

- **`install_claude`** (Function) — `src/slopgate/installer/_claude.py:106`
- **`uninstall_claude`** (Function) — `src/slopgate/installer/_claude.py:159`
- **`uninstall_codex`** (Function) — `src/slopgate/installer/_codex.py:265`
- **`cursor_user_hooks_path`** (Function) — `src/slopgate/installer/_cursor.py:53`
- **`cursor_project_hooks_path`** (Function) — `src/slopgate/installer/_cursor.py:57`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `install_claude` | Function | `src/slopgate/installer/_claude.py` | 106 |
| `uninstall_claude` | Function | `src/slopgate/installer/_claude.py` | 159 |
| `uninstall_codex` | Function | `src/slopgate/installer/_codex.py` | 265 |
| `cursor_user_hooks_path` | Function | `src/slopgate/installer/_cursor.py` | 53 |
| `cursor_project_hooks_path` | Function | `src/slopgate/installer/_cursor.py` | 57 |
| `install_cursor` | Function | `src/slopgate/installer/_cursor.py` | 154 |
| `uninstall_cursor` | Function | `src/slopgate/installer/_cursor.py` | 185 |
| `normalize_install_scope` | Function | `src/slopgate/installer/_install_scope.py` | 45 |
| `resolve_project_root` | Function | `src/slopgate/installer/_install_scope.py` | 54 |
| `scope_paths` | Function | `src/slopgate/installer/_install_scope.py` | 63 |
| `resolve_scoped_install_paths` | Function | `src/slopgate/installer/_install_scope.py` | 77 |
| `warn_residual_install_scope` | Function | `src/slopgate/installer/_install_scope.py` | 145 |
| `opencode_user_plugin_path` | Function | `src/slopgate/installer/_opencode.py` | 42 |
| `install_opencode` | Function | `src/slopgate/installer/_opencode.py` | 82 |
| `uninstall_opencode` | Function | `src/slopgate/installer/_opencode.py` | 137 |
| `pi_user_extension_path` | Function | `src/slopgate/installer/_pi.py` | 66 |
| `pi_project_extension_path` | Function | `src/slopgate/installer/_pi.py` | 77 |
| `install_pi` | Function | `src/slopgate/installer/_pi.py` | 249 |
| `uninstall_pi` | Function | `src/slopgate/installer/_pi.py` | 302 |
| `require_json_object` | Function | `src/slopgate/installer/_shared.py` | 258 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Uninstall_autoupdate → _binary_is_runnable` | cross_community | 6 |
| `Install_pi → _json_object_from_content` | cross_community | 6 |
| `Install_autoupdate → _binary_is_runnable` | cross_community | 6 |
| `Install_codex → Is_windows` | cross_community | 5 |
| `Install_codex → _posix_daemon_proxy_script` | cross_community | 5 |
| `Install_claude → Is_windows` | cross_community | 5 |
| `Install_claude → _posix_daemon_proxy_script` | cross_community | 5 |
| `Install_cursor → Is_windows` | cross_community | 5 |
| `Install_cursor → _posix_daemon_proxy_script` | cross_community | 5 |
| `Uninstall_opencode → Is_windows` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Suite | 7 calls |
| Cli | 5 calls |
| Util | 4 calls |
| Search | 1 calls |

## How to Explore

1. `context({name: "install_claude"})` — see callers and callees
2. `query({search_query: "installer"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
