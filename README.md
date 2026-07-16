# slopgate

Global CLI guardrails engine for AI coding agents. **Real-time guardrails where the host platform supports them, plus batch code quality linting.** Claude Code has the richest runtime surface; Cursor, Codex CLI, OpenCode, and Pi are supported with platform-specific limitations.

![Slopgate analytics dashboard — decision volume, event pipeline, top rules, severity mix](docs/assets/dashboard-overview.png)

## Install

Install [uv](https://docs.astral.sh/uv/) first, then either install the global CLI or work from a project venv.

```bash
# Global CLI on PATH (recommended)
uv tool install .

# From PyPI — published as `ai-slopgate` (the `slopgate` name was already taken)
# uv tool install ai-slopgate

# Development: project venv + dev tools
uv sync
uv run slopgate test
```

## Quick Start

```bash
# Initialize config (creates config.json in the active slopgate config dir)
slopgate config init
slopgate config path   # print the active config.json location

# Install hooks for your platform
slopgate install claude    # patches ~/.claude/settings.json
slopgate install codex     # patches ~/.codex/hooks.json
slopgate install opencode  # copies plugin to the user OpenCode plugins dir
slopgate install pi        # copies extension to ~/.pi/agent/extensions/

# Or use the native all-harness installer; auto-update is explicit opt-in
slopgate install all
slopgate install all --enable-autoupdate

# Run self-test
slopgate test

# Check stats
slopgate stats --days 7

# Lint the current project for code quality
slopgate lint check             # scan project; fail only on NEW violations (agent stop hooks)
slopgate lint strict            # fail on ANY violation (git pre-commit gate)
slopgate lint check --details   # extended violations + repair prognosis
slopgate lint init .            # scaffold slopgate.toml
```

## Dashboard

The [`dashboard/`](dashboard/) app visualizes Slopgate JSONL traces from the configured trace directory (by default `config_dir()/logs`): decision volume, top rules, sessions, harness status, and rule toggles. It complements `slopgate stats` with interactive charts, config editing, and file upload.

### Live dashboard (default: port 18834)

Build static assets with trace data baked in, deploy to the canvas directory, then run the API/static server:

```bash
# From repo root — local logs on this machine
make dashboard-build

# Or fetch logs + config from a remote host over SSH (default host: little)
make dashboard-build-ssh

# Serve UI + live APIs (snapshot, SSE stream, config read/write, harness status)
make dashboard-api
```

Open **http://192.168.50.151:18834/** on the LAN or **http://airbox:18834/** on the tailnet. The API binds to all IPv4 interfaces by default so both addresses work; set `BIND=127.0.0.1` to restrict ForceDash to local-only access.

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `18834` | HTTP listen port |
| `BIND` | `0.0.0.0` | Bind address for LAN/tailnet access (`192.168.50.151`, `airbox`) |
| `SLOPGATE_SSH_HOST` | `little` | SSH host for live logs, config, and harness APIs |
| `SLOPGATE_CONFIG_PATH` | `~/.config/slopgate/config.json` | Remote config file path used by the dashboard API |
| `SLOPGATE_TRACE_DIR` | `~/.config/slopgate/logs` | Remote trace directory used by the dashboard API |

`serve.py` serves files from `~/.openclaw/canvas/forcedash` (populated by `build-standalone.py`). Without a prior build, start `serve.py` only after `build-standalone.py` has run at least once.

### UI development (port 18835)

For frontend work without the canvas deploy path:

```bash
npm --prefix dashboard install   # or: bun --cwd dashboard install
make dashboard-dev                # Vite → http://localhost:18835
```

- Starts with **mock** data unless `window.__SLOPGATE_DATA__` is injected.
- **Drop** `.jsonl` / `.ndjson` trace files onto the UI to explore local logs.
- Rule editing and harness panels need `make dashboard-api` on **18834**; Vite proxies `/api/*` to that server.

### Trace inputs

| Source | How |
|---|---|
| Hooks (live) | `events.jsonl`, `rules.jsonl`, `results.jsonl`, `subprocess.jsonl` under `~/.config/slopgate/logs/` |
| CLI summary | `slopgate stats --days 7` (terminal; no UI) |
| Dashboard upload | Drag JSONL files in dev mode |
| Baked build | `build-standalone.py` inlines recent history into the deployed `index.html` |

## Supported Platforms

| Platform | Status | Install |
|---|---|---|
| **Claude Code** | ✅ Production | `slopgate install claude [--install-scope user\|project\|both]` |
| **Cursor** | ⚠️ Partial | `slopgate install cursor [--install-scope user\|project\|both]` |
| **Codex CLI** | ⚠️ Partial | `slopgate install codex [--install-scope user\|project\|both]` |
| **OpenCode** | ⚠️ Degraded | `slopgate install opencode [--install-scope user\|project\|both]` |
| **Pi** | ⚠️ Partial | `slopgate install pi [--install-scope user\|project\|both]` |

`slopgate install all` is the multi-device path: each enrolled device installs hooks only for harnesses that already exist on that OS/user profile. Auto-update is off by default; pass `--enable-autoupdate` to register the native scheduler for that OS using the pinned package source. Linux uses a user `systemd` timer, macOS uses a LaunchAgent, and native Windows uses `schtasks` plus a PowerShell shim. Use `--include-missing` only when intentionally creating every supported harness config on that device.

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

The package-managed prompt sync commands are `slopgate bundle sync-prompts` and `slopgate bundle uninstall-prompts`.

For Claude Code marketplace work, `bundle/claude-plugin/` is a plugin-shaped tree and `bundle/marketplace/` is a local marketplace catalog. Build/test locally with:

```bash
./bundle/scripts/build-claude-plugin.sh --copy
claude --plugin-dir ./bundle/claude-plugin
```

## Platform Notes

- **Claude Code**: full first-class hook target. Installs into `~/.claude/settings.json` and/or `.claude/settings.json` (`--install-scope`). Slopgate uses Claude's `hookSpecificOutput` permission and `decision`/`reason` shapes per the [hooks reference](https://code.claude.com/docs/en/hooks).
- **Cursor**: native hooks via `~/.cursor/hooks.json` (user) and/or `.cursor/hooks.json` (project). Install with `slopgate install <platform>` (user default), `--install-scope project|both`, and optional `--project-root /path/to/repo`. The same flags apply to `install all`, `setup`, `update`, and `uninstall`. Slopgate maps Cursor events to its canonical model and renders Cursor-native stdout (`permission` gates, `continue` for `beforeSubmitPrompt`, `additional_context` for `postToolUse`/`afterFileEdit`, `followup_message` for `stop`/`subagentStop`). Post-tool hooks cannot hard-block edits the way Claude `PostToolUse` denial does; use `preToolUse`, `beforeShellExecution`, or `beforeReadFile` for enforcement. Tab hooks (`beforeTabFileRead`, `afterTabFileEdit`) are installed for inline-completion policy; `workspaceOpen` is not wired yet.
- **Codex CLI**: partial hooks via `~/.codex/hooks.json` and/or `.codex/hooks.json`, with `features.hooks = true` enabled in the adjacent `config.toml` when that file exists. Matchers target `Bash|apply_patch|Edit|Write`. Post-tool critical blocks use Codex's top-level `continue`/`stopReason`; other findings use `hookSpecificOutput.additionalContext` or `decision`/`reason` per [Codex hooks docs](https://developers.openai.com/codex/config-reference).
- **OpenCode**: plugin shim at the user config plugins dir and/or `.opencode/plugins/slopgate-plugin.ts`. Native events (`tool.execute.before`, `tool.execute.after`, `file.edited`, `permission.asked`, `permission.replied`, `session.created`, `session.compacted`, `session.idle`, `session.error`, `session.status`, `shell.env`, and `command.executed`) are forwarded into Slopgate's canonical model. Blocking is strongest at `tool.execute.before`; `file.edited` is the preferred post-edit quality/lint signal when OpenCode emits it. Lifecycle/telemetry events are replayable and may log advisory context, but do not provide hard enforcement. `session.idle` stop guidance is advisory (`action: continue`) because OpenCode cannot force another turn from the plugin API.
- **Pi**: extension shim at `~/.pi/agent/extensions/pi-slopgate/index.ts` and/or `.pi/extensions/pi-slopgate/index.ts`. Native events (`tool_call`, `tool_result`, `tool_execution_end`, `user_bash`, `input`, `before_agent_start`, `turn_end`, and `agent_end`) are forwarded into Slopgate's canonical model. Blocking is strongest at `tool_call`, where Pi supports `{ block: true, reason }` and mutable `event.input` for argument patches; `user_bash` blocks are returned as synthetic failed shell results because Pi's user-bash hook is an interception surface, not the same block schema as model tool calls. The `input` event can return Pi's documented handled action for blocked prompts. Post-tool findings attach Slopgate metadata through Pi's `tool_result` patch shape, while visible Slopgate activity is sent as compact custom chat messages instead of footer/status widgets or routine stderr output. Installs migrate away the legacy standalone `slopgate.ts` shim when it is Slopgate-owned to avoid duplicate Pi extension loading.

## Architecture

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ Claude Code  │  │   Cursor    │  │  Codex CLI  │  │OpenCode/Pi │
│ settings.json│  │ hooks.json  │  │ hooks.json  │  │TS extension│
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
              │ 89 hook rules      │
              │ (44 Py + 45 regex) │
              └─────────┬──────────┘
                        ▼
              ┌────────────────────┐
              │  Platform Adapter  │
              │  (per-platform)    │
              └────────────────────┘
```

No shell wrappers. No bootstrap scripts. Just `slopgate handle` on PATH.

## CLI

### Hook runtime

```bash
slopgate daemon [--socket PATH] [--max-requests N]
slopgate handle [--platform claude|cursor|codex|opencode|pi]
slopgate handle-async
slopgate replay --payload fixture.json [--platform codex] [--pretty]
```

`slopgate handle` is the entrypoint that platform hooks invoke. `slopgate daemon` runs the optional resident Unix-socket server, and `handle-async` runs post-edit jobs when a platform supports them.

Record the structured contract required before the first edit to a target:

```bash
slopgate contract record \
  --session-id SESSION_ID \
  --target src/example.py \
  --operation Edit \
  --reuse "existing state facade and fixture convention" \
  --stable-behavior "preserve public constructors and hook output shapes" \
  --risk "constructor compatibility" \
  --risk "path normalization" \
  --risk "cross-session leakage" \
  --design-response "add one locked state section and one repo-strict rule" \
  --verification "run focused state, rule, and CLI tests"
```

`WORKFLOW-FIRST-WRITE-001` defaults to **shadow**: missing contracts are traced but do not block or inject context. Roll out per repo with the existing rule-surface contract:

```toml
[rule_surfaces.WORKFLOW-FIRST-WRITE-001.hook]
enabled = true
action = "context" # advisory; use "deny" for supported pre-edit blocking
```

Set `enabled = false` to disable observation. Blocking is limited to normalized edit-like `PreToolUse` and `PermissionRequest` surfaces; adapters keep their native output shapes. Contracts are keyed by normalized session and target, carry schema/timestamp metadata but no source content, and are consumed after the matching `PostToolUse` mutation.

Projected pre-edit lint uses complete reconstructable Python content only. It materializes proposed files in a disposable repository-relative overlay, runs deterministic file/touched collectors, restores real finding paths, and removes the overlay on every exit. Missing or ambiguous content is advisory; `QUALITY-LINT-001` remains the authoritative post-edit backstop.

Semantic retry state keeps exact fingerprints for diagnostics but counts churn by normalized session, rule, and path. After repeated denial, `slopgate recovery record` accepts changed-design evidence; only a successful full post-tool read after the lock counts as reread proof. Prompt keywords do not unlock retry state.

The optional repository failure profile stores only 30-day decayed aggregate dimensions. Inspect it with `slopgate profile show` and remove it with `slopgate profile clear`; worktrees remain distinct and no prompts, patches, source, raw paths, or raw sessions are stored.

### Repo enrollment and status

```bash
slopgate check [path]
slopgate enroll [path] [--no-worktrees]
```

`slopgate check` reports whether a path is enrolled, relaxed, skipped, or not enrolled. `slopgate enroll` writes the repo marker and can include git worktrees.

### Install / update / lifecycle

```bash
slopgate install <claude|cursor|codex|opencode|pi|all> [--dry-run] [--enable-autoupdate] [--include-missing] [--interval-minutes N] [--install-scope user|project|both] [--project-root PATH]
slopgate uninstall <claude|cursor|codex|opencode|pi|all> [--dry-run] [--enable-autoupdate] [--install-scope user|project|both] [--project-root PATH]
slopgate setup [--dry-run] [--enable-autoupdate] [--include-missing] [--interval-minutes N] [--install-scope user|project|both] [--project-root PATH]
slopgate update [--dry-run] [--source URL] [--include-missing] [--refresh-hooks] [--install-scope user|project|both] [--project-root PATH]
slopgate migrate [path] [--dry-run] [--force] [--user-only] [--repo-only]
```

`install all` only targets harnesses that already exist unless `--include-missing` is set. `--enable-autoupdate` explicitly installs the periodic package updater.

### Activity, config, and self-test

```bash
slopgate stats [--log results.jsonl] [--days N] [--json]
slopgate stats [--log results.jsonl] [--days N] --export-evidence PATH [--sample-size N]
slopgate profile <show|clear|reset> [--cwd PATH]
slopgate config show
slopgate config init [--force]
slopgate config path
slopgate test
slopgate version
```

#### PY-LOG-002 feedback-loop evidence

Export a deterministic, privacy-safe sample of the most recent PY-LOG-002
deny/block findings from `results.jsonl`:

```bash
uv run slopgate stats --days 42 \
  --export-evidence docs/evidence/feedback-loop-py-log-002-sample-2026-07-16.json \
  --sample-size 100
```

The JSON artifact contains redacted event metadata, hashed session/path/function
identifiers, trace locators, classification placeholders, and reviewer-status
placeholders. It never copies prompts, patches, tool inputs, proposed content,
source/code snippets, messages, additional context, raw metadata, output payloads,
raw paths, or raw session IDs. The exporter pins the pre-implementation
PY-LOG-002 source hash and fails if that rule source changes; this evidence work
does not change PY-LOG-002 severity or detection heuristics.

Classification values are `unclassified`, `true_positive`, `false_positive`,
and `needs_context`. Reviewer status is `pending`, `agreed`, or `disagreed`.
The current 100-record audit is documented in the matching `review`, `agreement`,
`adjudication`, and `replay` artifacts under `docs/evidence/`. Final adjudicated
counts are 19 true positives, 64 false positives, and 17 needing context. All 100
records were replayed in isolated state: 37 matched, 21 produced changed finding
metadata, and 42 no longer produced `PY-LOG-002`. The evidence gate is complete,
but the audit decision keeps severity and boundary behavior unchanged.

### Batch code quality linting (project-local)

```bash
slopgate lint check [--details|--verbose]
slopgate lint strict [--details|--verbose]
slopgate lint test-integrity [--details|--verbose]
slopgate lint freeze [path]
slopgate lint init [path]
slopgate lint update [path] [--dry-run]
```

`slopgate lint baseline` is intentionally disabled. `lint check` fails only on new violations; `lint strict` fails on any violation. `lint freeze` is the one-time baseline snapshot while `baselines.json` is empty.

Set the lint baseline file under `[paths]` in `slopgate.toml` (relative paths are resolved from the repo root):

```toml
[paths]
baseline_path = "baselines.json"
```

`slopgate lint check` prints the resolved baseline path in its header and **syncs `baselines.json` after each run**: on a clean pass it mirrors current findings (dropping stale ids); when NEW violations block the gate it only prunes fixed debt (never auto-adds NEW ids). Run `slopgate lint freeze` once while `rules` is still empty for initial enrollment. Listed stable IDs remain real defects to fix — not permission to ignore them.

#### 49 batch lint detectors

Separate from hook rule IDs: `slopgate lint check` runs these AST/static detectors project-wide (baseline-gated). The real-time hook `QUALITY-LINT-001` reuses the same detector engine on touched files after edits.

| Category | Detectors |
|---|---|
| **Parse** | python-parse-error |
| **Code smells** | high-complexity, long-method, too-many-params, deep-nesting, feature-envy, god-class, dead-code, flat-sibling-files, oversized-module, oversized-module-soft |
| **Type safety** | banned-any, type-suppression |
| **Exception safety** | broad-except-swallow, silent-except, silent-datetime-fallback |
| **Test smells** | long-test, eager-test, assertion-free-test, assertion-roulette, conditional-assertion, fixture-outside-conftest |
| **Test integrity** | untested-production-code, missing-integration-test, hypothesis-candidate, obsolete-or-deprecated-test, weak-test-assertion, mock-theater, schema-bypass-test-data, hand-built-test-payload, mocked-integration-test |
| **Duplication** | semantic-clone, repeated-magic-number, repeated-string-literal, repeated-code-block, duplicate-call-sequence |
| **Logging** | boundary-logging, direct-get-logger, wrong-logger-name |
| **Imports** | import-alias, import-fanout, private-import-chain |
| **LangGraph** | langgraph-deprecated-api, langgraph-state-mutation, langgraph-state-reducer |
| **Async** | pytest-asyncio-pattern |
| **Stale code** | deprecated-pattern |
| **Wrappers** | unnecessary-wrapper |
| **Style** | long-line |

## Config Discovery

slopgate resolves config in this order:

1. `$SLOPGATE_CONFIG` (explicit file path)
2. `config_dir()/config.json`, where `config_dir()` resolves from `$SLOPGATE_CONFIG_DIR`, then native Windows `%APPDATA%\slopgate`, then `$XDG_CONFIG_HOME/slopgate`, then `~/.config/slopgate`
3. `$CLAUDE_HOOK_LAYER_ROOT/.claude/hook-layer/config.json` or `$HOOK_LAYER_ROOT/.claude/hook-layer/config.json` (legacy)
4. `~/.claude/hooks/enforcer/.claude/hook-layer/config.json` (legacy default)
5. Bundled defaults

Trace and prompt-root discovery use `$SLOPGATE_ROOT` first, then the config directory, then the legacy hook-layer roots.

Per-repo overrides live in `slopgate.toml` in the repo root.

## Rules

Slopgate has **three surfaces** that are easy to conflate:

| Surface | Count (bundled defaults) | When it runs |
|---|---:|---|
| **Real-time hooks** | **89** rule evaluations | Agent tool events (`slopgate handle`) |
| ↳ Python classes | 44 (3 always-on + 41 repo-strict) | Path/git/AST quality, first-write contracts, projected lint, post-edit lint bridge, stop/session, LangGraph, etc. |
| ↳ Regex (`config.json`) | 45 | Pattern rules for Python/TS/Rust/shell/git/config paths |
| **Batch lint** | **49** detectors | `slopgate lint check` (project-wide, baseline-gated) |

Many IDs overlap *by design* (for example `PY-CODE-013` in hooks and `god-class` / wrapper detectors in batch lint). The dashboard “top rules” chart is dominated by high-volume hook IDs such as `QUALITY-LINT-001` (post-edit touched-file lint), `PY-LOG-002`, and `PY-CODE-013` — not by the older “30 + 39” inventory.

Repo mode still applies: **outside_repo** runs only the 3 always-on safety rules; **repo_strict** (with `slopgate.toml`) runs the full 89; **repo_relaxed** drops repo-strict families but keeps always-on safety.

### Real-time hook rules (44 Python + 45 regex)

- **Always-on (3):** protected paths, sensitive data, system paths
- **Workflow & quality (repo-strict):** first-write contracts, full-file read, git `--no-verify`, search reminders, post-edit quality commands, `QUALITY-LINT-001` / `QUALITY-POST-001`, baseline guard, enrollment, hook-infra protection, rulebook security, config-change guard, session/stop controls, bash error reinforcement
- **Python AST (19):** `PY-AST-001`, `PY-CODE-008`–`018`, `PY-EXC-001`/`002`, `PY-IMPORT-001`–`003`, `PY-LOG-002`, `PY-TEST-005`, etc.
- **LangGraph (3):** state reducers, mutation, deprecated API
- **Regex (45):** type/exception/logging/test/shell/QA-path/TS/Rust patterns in bundled `defaults.json` (override via `~/.config/slopgate/config.json`)

Availability depends on platform support:

- **Claude Code**: widest runtime coverage
- **Cursor**: partial — native `hooks.json` with Cursor-specific stdout shapes; strongest blocking on `preToolUse`, `beforeShellExecution`, and `beforeReadFile` (post-tool hooks are advisory/context-only, not hard blocks like Claude `PostToolUse` denial)
- **Codex CLI**: currently limited by Codex's narrower hook surface
- **OpenCode**: mediated through plugin event translation with advisory gaps around prompt and stop control
- **Pi**: mediated through extension event translation; strongest blocking on `tool_call`, with lifecycle and post-tool gaps where Pi only supports result patches or advisory extension behavior

### Batch lint (49 detectors)

- See the **49 batch lint detectors** table under Code Quality Linting
- Configured per repo via `slopgate.toml`; only *new* violations fail the gate
- Repo-wide baseline regeneration is disabled to prevent agents from normalizing technical debt

### Declarative regex rules (45)

Configured in `config.json` (`regex_rules` in bundled defaults) — covers Python/TS/Rust quality and test patterns, shell bypasses, QA path protection, linter config guards, git reminders, and more. Disable or downgrade per rule via `disabled_rules` / `severity_overrides`.

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
