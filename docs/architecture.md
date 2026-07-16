# Architecture

## Overview

slopgate is a global CLI guardrails engine for AI coding agents. One canonical rule pipeline serves Claude Code, Cursor, Codex CLI, OpenCode, and Pi without shell wrappers.

| Platform | Capability posture | Strongest feedback surface |
|---|---|---|
| Claude Code | Full | Pre-tool/permission blocking and post-tool backstops |
| Cursor | Partial | Pre-tool blocking; post-edit context only |
| Codex CLI | Partial | Available permission hooks; critical post-tool stop where supported |
| OpenCode | Degraded | `tool.execute.before`; post-edit and stop guidance are advisory |
| Pi | Partial | `tool_call`/input blocking; post-tool result patches and advisory messages |

All platforms follow `normalize_payload → state/preflight → rules → enrichment → adapter render → trace`. Capability labels gate documentation and rendering claims; they do not pretend that every harness can hard-block every event.

## Pipeline

Every hook invocation follows this flow:

1. **Receive** — platform sends JSON payload to stdin
2. **Normalize** — adapter translates platform-specific JSON → canonical form
3. **Context** — build HookContext (config, payload, trace writer)
4. **Skip check** — repo opt-out (sentinel files, slopgate.toml, skip_paths)
5. **Preflight** — check first-write contracts and project reconstructable edits in a disposable overlay
6. **Evaluate** — iterate all rules that support this event
7. **Retry/profile** — apply semantic retry state, structured recovery, and opt-in aggregate capture
8. **Enrich** — augment findings with project-specific context (fixtures, patterns, etc.)
9. **Render** — adapter translates findings → platform-native JSON for stdout
10. **Trace** — log results, parity metadata, and shadow observations

## Decision ordering

When multiple rules fire, the most restrictive decision wins:

```
deny/block > ask > allow > none (context-only)
```

## Modules

```
src/slopgate/
├── cli/                CLI entry points and hook runtime
├── engine/             Core evaluation and semantic retry pipeline
├── config/             XDG and per-repo config loading
├── context.py          Payload → HookContext
├── models.py           Data models (Severity, RuleFinding, RuntimeConfig, etc.)
├── trace.py            JSONL tracing
├── enrichment.py       Project-aware context enrichment for findings
├── constants.py        Tool name sets, language mappings
├── installer/         Platform-specific hook/plugin installation
├── stats/              Activity analysis and evidence export
├── state/              Locked cross-subprocess contracts, reads, retries, recovery
├── failure_profile/    Opt-in aggregate-only repository failure profile
├── adapters/
│   ├── base.py         Abstract PlatformAdapter
│   ├── claude.py       Claude Code (default, identity normalization)
│   ├── cursor.py       Cursor native hook mapping
│   ├── codex.py        Codex CLI
│   ├── opencode.py     OpenCode plugin mapping
│   └── pi.py           Pi extension mapping
├── rules/
│   ├── base.py         Abstract Rule class
│   ├── common/         Shared safety and authoritative post-edit rules
│   ├── first_write_contract.py
│   ├── projected_lint/ Disposable pre-edit projection and parity
│   ├── regex_rule.py   Config-driven regex rule engine
│   ├── python_ast.py   19 AST-backed Python quality rules
│   ├── stop_rules.py   8 rules (stop checks, session start, config guard, etc.)
│   ├── baseline_guard.py   Baseline inflation protection
│   ├── error_rules.py  Bash error/failure reinforcement
│   └── langgraph.py    LangGraph-specific best practices
├── util/
│   ├── payloads.py     Payload normalization, path extraction, content extraction
│   └── subprocesses.py Shell command runner
└── resources/
    ├── defaults.json       Bundled default config
    ├── opencode_plugin.ts  OpenCode plugin template
    └── prompt_context/     Bundled prompt context files
```

## Config discovery

slopgate resolves config in order:

1. `$SLOPGATE_CONFIG` — explicit file path
2. `~/.config/slopgate/config.json` — XDG standard
3. `$CLAUDE_HOOK_LAYER_ROOT/.claude/hook-layer/config.json` — legacy
4. `~/.claude/hooks/enforcer/.claude/hook-layer/config.json` — legacy default
5. Bundled `resources/defaults.json` — fallback

Per-repo overrides via `slopgate.toml`:

```toml
[slopgate]
disabled_rules = ["PY-CODE-013"]
[slopgate.severity_overrides]
"PY-CODE-008" = "warn"
[thresholds]
max_method_lines = 80
```

## Trace and replay

Every evaluation writes to `~/.config/slopgate/logs/`:

- `events.jsonl` — event summaries
- `rules.jsonl` — per-rule matches with metadata
- `results.jsonl` — final rendered output + all findings
- `subprocess.jsonl` — synchronous subprocess runs
- `async/subprocess.jsonl` — async post-edit jobs

Replay any captured payload:

```bash
slopgate replay --payload fixture.json --platform codex --pretty
```

## Extension

Two paths:

**Regex rules** (fastest) — add to `config.json`:
```json
{
  "rule_id": "CUSTOM-001",
  "title": "Block X",
  "events": ["PreToolUse"],
  "target": "content",
  "patterns": ["some_pattern"],
  "action": "deny",
  "message": "Blocked because..."
}
```

**Python rules** (full power) — subclass `Rule` in `rules/`, register in `rules/__init__.py`.
