---
name: rtk-cli
description: Use when running shell commands in agent sessions to cut Bash output tokens, or when the user asks to install/configure RTK, reduce context from git/test/lint commands, or use rtk git/rg/cargo wrappers. Triggers on "rtk", "token savings", "compact git status", or heavy command output eating context.
---

# rtk-cli

[RTK](https://github.com/rtk-ai/rtk) is a Rust CLI proxy that filters and compresses common dev command output (often 60–90% fewer tokens) before it reaches the model. It complements Slopgate: **Slopgate enforces quality on edits**; **RTK shrinks read-only shell output**.

Upstream: https://github.com/rtk-ai/rtk

## Install

```bash
# macOS
brew install rtk

# Linux/macOS (installs to ~/.local/bin)
curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh

# From source
cargo install --git https://github.com/rtk-ai/rtk
```

Verify: `rtk --version` and `rtk gain`. If `rtk gain` fails, you may have the unrelated crates.io "rtk" package — use the git install above.

## Harness setup (hooks owned by RTK, not the bundle)

Run **after** `slopgate install …` when both are used. The bundle does not symlink `hooks.json` or `settings.json`.

| Harness | Command |
|---|---|
| Claude Code / Copilot | `rtk init -g` |
| Cursor | `rtk init -g --agent cursor` |
| Codex | `rtk init -g --codex` |
| OpenCode | `rtk init -g --opencode` |
| Gemini CLI | `rtk init -g --gemini` |

Restart the harness after init. Uninstall RTK hooks only: `rtk init -g --uninstall`.

**Scope:** auto-rewrite applies to **Bash/shell tool** commands only. Built-in `Read` / `Grep` / `Glob` (Claude/Cursor) are not rewritten — use shell (`cat`/`head`, `rtk rg`, `find`) or explicit `rtk read` / `rtk grep` / `rtk find` when you want compact output.

## Slopgate + RTK together

1. `slopgate install all` (or per-platform) — quality guardrails via `slopgate handle`.
2. `rtk init -g` (with the right `--agent` / `--codex` / `--opencode` flags) — Bash rewrite to `rtk …` equivalents.
3. Confirm both hook entries exist (e.g. Cursor `~/.cursor/hooks.json`: Slopgate `slopgate handle` + RTK `preToolUse` rewrite).

Slopgate rules already assume RTK for search in several shards (`rtk rg`, not GNU `grep` for ripgrep flags). See `~/.claude/rules/search-navigation.md` when linked from the bundle.

## High-value commands

```bash
rtk git status
rtk git diff
rtk git log -n 20
rtk rg "pattern" src/
rtk read path/to/file.rs
rtk cargo test
rtk pytest
rtk ruff check
rtk docker ps
rtk gain                 # savings stats
rtk discover             # missed rewrite opportunities
```

Global flags: `-u` / `--ultra-compact` for extra compression; `-v` for more detail.

## Config

`~/.config/rtk/config.toml` (macOS also `~/Library/Application Support/rtk/config.toml`):

```toml
[hooks]
exclude_commands = ["curl"]   # never rewrite these

[tee]
enabled = true
mode = "failures"             # save full output on failure
```

Per-command bypass: `RTK_DISABLED=1 git status` runs raw.

## Telemetry

Opt-in only. `rtk telemetry status` | `enable` | `disable` | `forget`. Set `RTK_TELEMETRY_DISABLED=1` to block regardless of consent.

## When not to use RTK

- You need **full, unfiltered** output for debugging (use raw command or `RTK_DISABLED=1`).
- Piped workflows where rewriting the left side would break format expectations (RTK skips some `find`/`fd` pipe cases).
- Replacing Slopgate lint/hook enforcement — use `slopgate lint check` and hook denials for that.
