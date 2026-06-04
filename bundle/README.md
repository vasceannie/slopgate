# Slopgate agent bundle

`bundle/` centralizes Slopgate-facing agent assets that are safe to reuse across harnesses: recovery skills, rule shards, prompt fragments, agents, and MCP templates.

## Responsibilities

| Surface | Owner |
|---|---|
| Skills, agents, prompt fragments, non-hook rule shards | `bundle/` + `bundle/scripts/link-local.sh` |
| Claude/Codex/Cursor `hooks.json` or Claude `settings.json` hook commands | `slopgate install ...` only |
| OpenCode runtime plugin template | `src/slopgate/resources/` + `slopgate install opencode` |
| Dashboard/static app | `dashboard/` |

Do **not** symlink over full user prompt entrypoints such as `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, or `~/.config/opencode/AGENTS.md`. The bundle stores fragments under `bundle/*/prompts/`; merge or import those intentionally.

## Local development flow

```bash
uv tool install /path/to/slopgate  # global CLI; or `uv sync` for dev venv
./bundle/scripts/link-local.sh --dry-run
./bundle/scripts/link-local.sh
slopgate install all            # hooks only; idempotent owner of harness hook files
./bundle/scripts/verify-local.sh
```

Use `--only claude`, `--only opencode`, `--only codex`, or `--only cursor` to limit symlink work. Use `--force` only when you have reviewed the target; real files/directories are backed up before replacement.

## Directory map

- `shared/skills/` — canonical shared skill trees linked into Claude and OpenCode.
- `shared/mcp/slopgate.mcp.json` — placeholder MCP config template; servers are intentionally TBD.
- `claude/` — Claude-specific prompt fragments, rule shards, subagent rules, and agents.
- `opencode/` — OpenCode prompt fragments and rule shards; hooks remain installed by `slopgate install opencode`.
- `codex/` — Codex prompt fragments for manual merge into `~/.codex/AGENTS.md`.
- `cursor/` — reserved Cursor rule surface; native hooks remain installed by `slopgate install cursor`.
- `claude-plugin/` — Claude Code plugin-shaped tree for local `--plugin-dir` testing and future marketplace packaging.
- `marketplace/` — local Claude marketplace catalog for plugin-manager smoke tests.
- `scripts/` — manifest-driven link, unlink, verify, and plugin-build helpers.

## Claude plugin / marketplace flow

```bash
./bundle/scripts/build-claude-plugin.sh --copy   # release-style component copy
claude --plugin-dir ./bundle/claude-plugin       # local plugin smoke
# In Claude Code: /plugin marketplace add ./bundle/marketplace
```

The plugin contains skills and agents only. Its `hooks/README.md` points users back to `slopgate install claude` for live hook wiring.

## Migration inventory

The first bundle pass migrated these local Slopgate-branded assets:

- `code-hygiene-refactor`, `hygiene-orchestrator`, `isx-cli`, and `code-smell-utility-locator` into `shared/skills/`.
- `agent-python-executor.md` into `claude/agents/`.
- Claude rule shards `python/style-conventions.md` and `quality-complexity.md`.
- OpenCode rule shard `workflow/own-completion.md`.
- Slopgate-specific prompt fragments from Claude and OpenCode global guidance.
