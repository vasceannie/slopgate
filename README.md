# slopgate

Global CLI guardrails engine for AI coding agents. **Real-time guardrails where the host platform supports them, plus batch code quality linting.** Claude Code has the richest runtime surface; Codex CLI and OpenCode are supported with platform-specific limitations.

## Install

```bash
pipx install .
# or
pip install -e .
```

PowerShell:

```powershell
py -m pip install -e .
# or, when using pipx on Windows
pipx install .
```

## Quick Start

```bash
# Initialize config (creates ~/.config/slopgate/)
slopgate config init

# Install hooks for your platform
slopgate install claude    # patches ~/.claude/settings.json
slopgate install codex     # patches ~/.codex/hooks.json
slopgate install opencode  # copies plugin to the user OpenCode plugins dir

# Or use the native all-harness installer and OS auto-updater
slopgate install all --with-autoupdate

# Run self-test
slopgate test

# Check stats
slopgate stats --days 7

# Lint the current project for code quality
slopgate lint check             # scan the full project from the detected root
slopgate lint check --details   # extended violations + repair prognosis
slopgate lint init .            # scaffold slopgate.toml
```

## Supported Platforms

| Platform | Status | Install |
|---|---|---|
| **Claude Code** | ✅ Production | `slopgate install claude [--install-scope user\|project\|both]` |
| **Cursor** | ⚠️ Partial | `slopgate install cursor [--install-scope user\|project\|both]` |
| **Codex CLI** | ⚠️ Partial | `slopgate install codex [--install-scope user\|project\|both]` |
| **OpenCode** | ⚠️ Degraded | `slopgate install opencode [--install-scope user\|project\|both]` |

`slopgate install all --with-autoupdate` is the multi-device path: each enrolled device installs hooks only for harnesses that already exist on that OS/user profile, then registers the native scheduler for that OS. Linux uses a user `systemd` timer, macOS uses a LaunchAgent, and native Windows uses `schtasks` plus a PowerShell shim. The scheduler polls the GitHub source and runs `slopgate update-suite`, so a push to `github.com/vasceannie/slopgate` refreshes the package and rewrites the local Claude/Codex/OpenCode install sites when each device is online. Use `--include-missing` only when intentionally creating every supported harness config on that device. `install-suite --with-autoupdate` remains as a compatibility alias for the same all-harness flow.

## Agent bundle

The [`bundle/`](bundle/) directory is the repo-owned source of truth for Slopgate-facing agent assets that are safe to share across harnesses: recovery skills, rule shards, prompt fragments, Claude agents, and MCP templates.

Local development flow:

```bash
./bundle/scripts/link-local.sh --dry-run  # review symlink targets
./bundle/scripts/link-local.sh            # link skills/rules/agents only
slopgate install all                      # hook files remain CLI-owned
./bundle/scripts/verify-local.sh
```

Important ownership boundary: the bundle **does not** symlink full prompt entrypoints (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.config/opencode/AGENTS.md`) and does **not** own Claude/Codex/Cursor `hooks.json` or Claude `settings.json` hook commands. Keep hook wiring under `slopgate install ...` so install/uninstall can merge safely, back up user config, and point at the correct local binary.

For Claude Code marketplace work, `bundle/claude-plugin/` is a plugin-shaped tree and `bundle/marketplace/` is a local marketplace catalog. Build/test locally with:

```bash
./bundle/scripts/build-claude-plugin.sh --copy
claude --plugin-dir ./bundle/claude-plugin
```

## Platform Notes

- **Claude Code**: full first-class hook target. Installs into `~/.claude/settings.json` and/or `.claude/settings.json` (`--install-scope`). Slopgate uses Claude's `hookSpecificOutput` permission and `decision`/`reason` shapes per the [hooks reference](https://code.claude.com/docs/en/hooks).
- **Cursor**: native hooks via `~/.cursor/hooks.json` (user) and/or `.cursor/hooks.json` (project). Install with `slopgate install <platform>` (user default), `--install-scope project|both`, and optional `--project-root /path/to/repo`. The same flags apply to `install all`, `install-suite`, `update-suite`, and `uninstall`. Slopgate maps Cursor events to its canonical model and renders Cursor-native stdout (`permission` gates, `continue` for `beforeSubmitPrompt`, `additional_context` for `postToolUse`/`afterFileEdit`, `followup_message` for `stop`/`subagentStop`). Post-tool hooks cannot hard-block edits the way Claude `PostToolUse` denial does; use `preToolUse`, `beforeShellExecution`, or `beforeReadFile` for enforcement. Tab hooks (`beforeTabFileRead`, `afterTabFileEdit`) are installed for inline-completion policy; `workspaceOpen` is not wired yet.
- **Codex CLI**: partial hooks via `~/.codex/hooks.json` and/or `.codex/hooks.json`, with `features.hooks = true` enabled in the adjacent `config.toml` when that file exists. Matchers target `Bash|apply_patch|Edit|Write`. Post-tool critical blocks use Codex's top-level `continue`/`stopReason`; other findings use `hookSpecificOutput.additionalContext` or `decision`/`reason` per [Codex hooks docs](https://developers.openai.com/codex/config-reference).
- **OpenCode**: plugin shim at the user config plugins dir and/or `.opencode/plugins/slopgate-plugin.ts`. Native events (`tool.execute.before`, `tool.execute.after`, `session.created`, `session.idle`, `permission.asked`) map to the canonical model; blocking is strongest at `tool.execute.before`. `session.idle` stop guidance is advisory (`action: continue`) because OpenCode cannot force another turn from the plugin API.

## Architecture

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ Claude Code  │  │   Cursor    │  │  Codex CLI  │  │  OpenCode   │
│ settings.json│  │ hooks.json  │  │ hooks.json  │  │  TS plugin  │
└──────┬───────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                 │                 │                 │
       └─────────────────┴─────────────────┴─────────────────┘
                         ▼
              ┌────────────────────┐
              │  slopgate handle │
              │  --platform X      │
              └─────────┬──────────┘
                        ▼
              ┌────────────────────┐
              │   Rule Engine      │
              │  (30 Python rules  │
              │   + 39 regex rules)│
              └─────────┬──────────┘
                        ▼
              ┌────────────────────┐
              │  Platform Adapter  │
              │  (per-platform)    │
              └────────────────────┘
```

No shell wrappers. No bootstrap scripts. Just `slopgate handle` on PATH.

## CLI

### Hook Enforcement (real-time)

```bash
# Core hook handler (called by platform hooks)
slopgate handle [--platform claude|cursor|codex|opencode]

# Replay a captured payload
slopgate replay --payload fixture.json [--platform codex] [--pretty]

# Check quality gate status for a repo
slopgate check [path]

# Install/uninstall hooks
slopgate install <platform|all> [--with-autoupdate] [--dry-run]
slopgate uninstall <platform> [--dry-run]
slopgate install-suite [--with-autoupdate] [--dry-run]
slopgate update-suite [--dry-run]

# Activity analysis
slopgate stats [--log results.jsonl] [--days N] [--json]

# Configuration
slopgate config show        # show effective config
slopgate config init        # create from defaults
slopgate config path        # print config file location

# Self-test
slopgate test

# Version
slopgate version
```

For Codex CLI and OpenCode, "real-time" should be read as best-effort within the host platform's current hook or plugin surface, not as Claude-equivalent parity.

### Code Quality Linting (batch)

```bash
# Scan the current project root for violations (compares against baseline)
# Intentionally accepts no path/file argument; use cd <project-root> first.
slopgate lint check [--details|--verbose]

# Repo-wide rebaselining is intentionally disabled
# Do not run slopgate lint baseline [path]

# Scaffold a slopgate.toml config
slopgate lint init [path]

# Merge missing config keys into existing slopgate.toml
slopgate lint update [path] [--dry-run]
```

#### 28 Batch Detectors

| Category | Detectors |
|---|---|
| **Code smells** | high-complexity, long-method, too-many-params, deep-nesting, god-class, oversized-module |
| **Type safety** | banned-any (typing.Any), type-suppression (# type: ignore) |
| **Exception safety** | broad-except-swallow, silent-except, silent-datetime-fallback |
| **Test smells** | long-test, eager-test, assertion-free-test, assertion-roulette, conditional-assertion, fixture-outside-conftest |
| **Duplication** | semantic-clone, repeated-magic-number, repeated-string-literal, repeated-code-block, duplicate-call-sequence |
| **Logging** | direct-get-logger, wrong-logger-name |
| **Stale code** | deprecated-pattern |
| **Wrappers** | unnecessary-wrapper |
| **Style** | long-line |

## Config Discovery

slopgate resolves config in this order:

1. `$SLOPGATE_CONFIG` (explicit file path)
2. `%APPDATA%\slopgate\config.json` on native Windows
3. `~/.config/slopgate/config.json` (XDG/POSIX)
4. `$CLAUDE_HOOK_LAYER_ROOT/.claude/hook-layer/config.json` (legacy)
5. `~/.claude/hooks/enforcer/.claude/hook-layer/config.json` (legacy default)
6. Bundled defaults

Per-repo overrides via `slopgate.toml` in the repo root.

## Rules

### Real-time Hook Rules (30 Python + 39 regex)
- Path protection (protected, sensitive, system)
- Git safety (--no-verify, stash ban)
- Python AST quality (long methods, deep nesting, complexity, dead code, god class, feature envy, thin wrappers)
- Test quality (assertion roulette, test loops, fixtures placement, test smells)
- Error handling (bash output errors, failure reinforcement)
- Session controls (stop checks, config change guard)
- LangGraph best practices (state reducers, mutation detection, deprecated API)
- Baseline inflation guard

Availability depends on platform support:

- **Claude Code**: widest runtime coverage
- **Codex CLI**: currently limited by Codex's narrower hook surface
- **OpenCode**: mediated through plugin event translation with advisory gaps around prompt and stop control

### Batch Lint Rules (28 detectors)
- See "28 Batch Detectors" table above
- Configured via `slopgate.toml` in each project
- Baseline tracking: only *new* violations fail the gate
- Repo-wide baseline regeneration is disabled to prevent agents from normalizing technical debt

### Declarative Regex Rules (39)
Configured in `config.json` — covers:
- Python type safety (Any ban, suppression ban)
- Exception handling patterns
- Shell quality bypasses
- Linter config protection
- TODO/FIXME markers
- And more

## Per-Repo Overrides

Create `slopgate.toml` in your repo root:

```toml
[slopgate]
# Disable specific rules
disabled_rules = ["PY-CODE-013", "PY-TEST-004"]

# Downgrade rules to advisory
[slopgate.severity_overrides]
"PY-CODE-008" = "warn"

[thresholds]
max_method_lines = 80
max_params = 6
max_complexity = 15
max_nesting_depth = 5
max_line_length = 140
```

## Enforcement Modes

slopgate now enforces in two layers using `slopgate.toml` as the enrollment signal:

- **outside_repo**: no `slopgate.toml` in the current working repo root. Only always-on safety rules run.
- **repo_strict**: `slopgate.toml` exists and the repo is enabled. Always-on safety + full strict/project rules run.
- **repo_relaxed**: `slopgate.toml` exists, but `.noslopgate`, `.no-slop-gate`, or `[slopgate].enabled = false` is set. Only always-on safety rules run.

Always-on safety protections are:

- `BUILTIN-PROTECTED-PATHS`
- `GLOBAL-BUILTIN-SENSITIVE-DATA`
- `GLOBAL-BUILTIN-SYSTEM-PROTECTION`

`skip_paths` no longer bypasses the engine. Matching paths only suppress the repo-strict rule family; always-on safety still runs.

To place a repo into relaxed mode locally:

```bash
touch .noslopgate
```

Or in `slopgate.toml`:

```toml
[slopgate]
enabled = false
```

## Testing

```bash
cd slopgate
PYTHONPATH=src pytest tests/ -q
```

PowerShell:

```powershell
cd slopgate
$env:PYTHONPATH = "src"
pytest tests/ -q
```

## Windows / PowerShell Notes

- Native Windows installs use the standard console scripts generated by Python
  packaging (`slopgate.exe`, `vfc.exe`, and `isx.exe`).
- Installed hook commands are quoted through a PowerShell-compatible launcher
  on Windows so paths with spaces under `AppData` can execute reliably.
- PowerShell commands are inspected for common file operations such as
  `Set-Content`, `Add-Content`, `Out-File`, `Copy-Item`, `Move-Item`, and
  `Remove-Item`.
- OpenCode plugin installs use `%APPDATA%\\opencode\\plugins` on native
  Windows and bake the discovered `slopgate.exe` path into the generated
  plugin with JSON/TypeScript-safe escaping. `SLOPGATE_BIN` can still override
  it at runtime.
- Codex CLI hook support on native Windows depends on the installed Codex
  version. When Codex hooks are unavailable or degraded on Windows, use WSL or
  Git Bash for runtime enforcement and use `slopgate lint check` natively for
  batch quality checks.

## Archived Windows worktree

The old `slopgate-windows-powershell` git worktree (`windows-powershell-compat`) is
archived; native Windows support is in this repo. See
[docs/archive/windows-powershell-compat.md](docs/archive/windows-powershell-compat.md).

## Cutover from slopgate / Enforcer

```bash
# 0. One-shot rename (repos + user config + OpenCode plugin)
slopgate migrate
# Repo-only: slopgate migrate --repo-only /path/to/repo

# 1. Install slopgate globally
pipx install ~/path/to/slopgate

# 2. Copy your config
mkdir -p ~/.config/slopgate
cp ~/.claude/hooks/enforcer/.claude/hook-layer/config.json ~/.config/slopgate/

# 3. Install hooks (replaces shell wrappers)
slopgate install claude

# 4. Test
slopgate test

# 5. Remove old enforcer (optional)
# rm -rf ~/.claude/hooks/enforcer
```
