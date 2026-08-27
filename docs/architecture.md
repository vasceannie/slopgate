# Architecture

## Overview

slopgate is a global CLI guardrails engine for AI coding agents. One rule set, three platforms (Claude Code, Codex CLI, OpenCode), zero shell wrappers.

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ Claude Code  │  │  Codex CLI  │  │  OpenCode   │
│ settings.json│  │ hooks.json  │  │  TS plugin  │
│  ↓           │  │  ↓          │  │  ↓          │
│ slopgate   │  │ slopgate  │  │ slopgate  │
│   handle     │  │   handle    │  │   handle    │
│              │  │  --platform │  │  --platform │
│              │  │    codex    │  │   opencode  │
└──────┬───────┘  └──────┬──────┘  └──────┬──────┘
       │                 │                 │
       └─────────────────┼─────────────────┘
                         ▼
              ┌────────────────────┐
              │  Platform Adapter  │
              │  normalize_payload │
              └─────────┬──────────┘
                        ▼
              ┌────────────────────┐
              │   Rule Engine      │
              │  87 hook rules     │
              │  (42 Py + 45 rx)  │
              └─────────┬──────────┘
                        ▼
              ┌────────────────────┐
              │    Enrichment      │
              │  (project context) │
              └─────────┬──────────┘
                        ▼
              ┌────────────────────┐
              │  Platform Adapter  │
              │  render_output     │
              └────────────────────┘
```

## Pipeline

Every hook invocation follows this flow:

1. **Receive** — platform sends JSON payload to stdin
2. **Normalize** — adapter translates platform-specific JSON → canonical form
3. **Context** — build HookContext (config, payload, trace writer)
4. **Skip check** — repo opt-out (sentinel files, slopgate.toml, skip_paths)
5. **Evaluate** — iterate all rules that support this event
6. **Enrich** — augment findings with project-specific context (fixtures, patterns, etc.)
7. **Render** — adapter translates findings → platform-native JSON for stdout
8. **Trace** — log everything to JSONL

## Decision ordering

When multiple rules fire, the most restrictive decision wins:

```
deny/block > ask > allow > none (context-only)
```

## Modules

```
src/slopgate/
├── cli.py              CLI entry point (argparse subcommands)
├── engine.py           Core evaluation pipeline
├── config.py           XDG config discovery + loading
├── context.py          Payload → HookContext
├── models.py           Data models (Severity, RuleFinding, RuntimeConfig, etc.)
├── trace.py            JSONL tracing
├── enrichment.py       Project-aware context enrichment for findings
├── constants.py        Tool name sets, language mappings
├── installer/         Platform-specific hook/plugin installation
├── stats.py            Hook activity log analysis
├── async_jobs.py       Async post-edit quality jobs
├── adapters/
│   ├── base.py         Abstract PlatformAdapter
│   ├── claude.py       Claude Code (default, identity normalization)
│   ├── codex.py        Codex CLI
│   └── opencode.py     OpenCode (event name mapping, output translation)
├── rules/
│   ├── base.py         Abstract Rule class
│   ├── common.py       8 built-in rules (paths, git, sensitive data, etc.)
│   ├── regex_rule.py   Config-driven regex rule engine
│   ├── python_ast.py   10 AST-backed Python quality rules
│   ├── stop_rules.py   7 rules (stop checks, session start, config guard, etc.)
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
