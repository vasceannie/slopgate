# vibeforcer

Global CLI guardrails engine for AI coding agents. **Real-time guardrails where the host platform supports them, plus batch code quality linting.** Claude Code has the richest runtime surface; Codex CLI and OpenCode are supported with platform-specific limitations.

## Install

```bash
pipx install .
# or
pip install -e .
```

## Quick Start

```bash
# Initialize config (creates ~/.config/vibeforcer/)
vibeforcer config init

# Install hooks for your platform
vibeforcer install claude    # patches ~/.claude/settings.json
vibeforcer install codex     # patches ~/.codex/hooks.json
vibeforcer install opencode  # copies plugin to the user OpenCode plugins dir

# Run self-test
vibeforcer test

# Check stats
vibeforcer stats --days 7

# Lint the current project for code quality
vibeforcer lint check             # scan the full project from the detected root
vibeforcer lint check --details   # extended violations + repair prognosis
vibeforcer lint init .            # scaffold quality_gate.toml
```

## Supported Platforms

| Platform | Status | Install |
|---|---|---|
| **Claude Code** | ✅ Production | `vibeforcer install claude` |
| **Codex CLI** | ⚠️ Partial | `vibeforcer install codex` |
| **OpenCode** | ⚠️ Degraded | `vibeforcer install opencode` |

## Platform Notes

- **Claude Code**: full first-class hook target. Vibeforcer can use Claude's richer event model, including prompt/session/tool interception.
- **Codex CLI**: experimental hook support with narrower runtime coverage than Claude Code. Vibeforcer installs conservative Codex hooks for shell and common edit tools (`Bash|apply_patch|Edit|Write`) and treats Codex as partial coverage.
- **OpenCode**: implemented via a plugin shim rather than a Claude-style hook schema. OpenCode exposes plugin events such as `tool.execute.before`, `tool.execute.after`, `permission.asked`, and session events, but prompt interception and stop blocking do not have Claude-equivalent parity. The installer targets the user plugin directory (`~/.config/opencode/plugins/` on Linux/XDG, `%APPDATA%\\opencode\\plugins\\` on native Windows) and backs up existing plugin files before replacing owned content.

## Architecture

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ Claude Code  │  │  Codex CLI  │  │  OpenCode   │
│ settings.json│  │ hooks.json  │  │  TS plugin  │
└──────┬───────┘  └──────┬──────┘  └──────┬──────┘
       │                 │                 │
       └─────────────────┼─────────────────┘
                         ▼
              ┌────────────────────┐
              │  vibeforcer handle │
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

No shell wrappers. No bootstrap scripts. Just `vibeforcer handle` on PATH.

## CLI

### Hook Enforcement (real-time)

```bash
# Core hook handler (called by platform hooks)
vibeforcer handle [--platform claude|codex|opencode]

# Replay a captured payload
vibeforcer replay --payload fixture.json [--platform codex] [--pretty]

# Check quality gate status for a repo
vibeforcer check [path]

# Install/uninstall hooks
vibeforcer install <platform> [--dry-run]
vibeforcer uninstall <platform> [--dry-run]

# Activity analysis
vibeforcer stats [--log results.jsonl] [--days N] [--json]

# Configuration
vibeforcer config show        # show effective config
vibeforcer config init        # create from defaults
vibeforcer config path        # print config file location

# Self-test
vibeforcer test

# Version
vibeforcer version
```

For Codex CLI and OpenCode, "real-time" should be read as best-effort within the host platform's current hook or plugin surface, not as Claude-equivalent parity.

### Code Quality Linting (batch)

```bash
# Scan the current project root for violations (compares against baseline)
# Intentionally accepts no path/file argument; use cd <project-root> first.
vibeforcer lint check [--details|--verbose]

# Repo-wide rebaselining is intentionally disabled
# Do not run vibeforcer lint baseline [path]

# Scaffold a quality_gate.toml config
vibeforcer lint init [path]

# Merge missing config keys into existing quality_gate.toml
vibeforcer lint update [path] [--dry-run]
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

vibeforcer resolves config in this order:

1. `$VIBEFORCER_CONFIG` (explicit file path)
2. `~/.config/vibeforcer/config.json` (XDG)
3. `$CLAUDE_HOOK_LAYER_ROOT/.claude/hook-layer/config.json` (legacy)
4. `~/.claude/hooks/enforcer/.claude/hook-layer/config.json` (legacy default)
5. Bundled defaults

Per-repo overrides via `quality_gate.toml` in the repo root.

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
- Configured via `quality_gate.toml` in each project
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

Create `quality_gate.toml` in your repo root:

```toml
[quality_gate]
# Disable specific rules
disabled_rules = ["PY-CODE-013", "PY-TEST-004"]

# Downgrade rules to advisory
[quality_gate.severity_overrides]
"PY-CODE-008" = "warn"

[thresholds]
max_method_lines = 80
max_params = 6
max_complexity = 15
max_nesting_depth = 5
max_line_length = 140
```

## Enforcement Modes

vibeforcer now enforces in two layers using `quality_gate.toml` as the enrollment signal:

- **outside_repo**: no `quality_gate.toml` in the current working repo root. Only always-on safety rules run.
- **repo_strict**: `quality_gate.toml` exists and the repo is enabled. Always-on safety + full strict/project rules run.
- **repo_relaxed**: `quality_gate.toml` exists, but `.noqualitygate`, `.no-quality-gate`, or `[quality_gate].enabled = false` is set. Only always-on safety rules run.

Always-on safety protections are:

- `BUILTIN-PROTECTED-PATHS`
- `GLOBAL-BUILTIN-SENSITIVE-DATA`
- `GLOBAL-BUILTIN-SYSTEM-PROTECTION`

`skip_paths` no longer bypasses the engine. Matching paths only suppress the repo-strict rule family; always-on safety still runs.

To place a repo into relaxed mode locally:

```bash
touch .noqualitygate
```

Or in `quality_gate.toml`:

```toml
[quality_gate]
enabled = false
```

## Testing

```bash
cd vibeforcer
PYTHONPATH=src pytest tests/ -q
```

## Cutover from Enforcer

```bash
# 1. Install vibeforcer globally
pipx install ~/path/to/vibeforcer

# 2. Copy your config
mkdir -p ~/.config/vibeforcer
cp ~/.claude/hooks/enforcer/.claude/hook-layer/config.json ~/.config/vibeforcer/

# 3. Install hooks (replaces shell wrappers)
vibeforcer install claude

# 4. Test
vibeforcer test

# 5. Remove old enforcer (optional)
# rm -rf ~/.claude/hooks/enforcer
```
