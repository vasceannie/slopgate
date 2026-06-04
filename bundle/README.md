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

- `shared/skills/` — canonical shared skill trees linked into Claude, OpenCode, and Codex.
- `shared/mcp/slopgate.mcp.json` — placeholder MCP config template; servers are intentionally TBD and must stay secret-free.
- `shared/mcp/codegraph.mcp.json` — merge snippet for the CodeGraph MCP server (`codegraph serve --mcp`); prefer `codegraph install` for agent wiring.
- `claude/` — Claude-specific prompt fragments, full rule shard mirror, subagent-rule digests, and agents.
- `opencode/` — OpenCode prompt fragments and full rule shard mirror; hooks remain installed by `slopgate install opencode`.
- `codex/` — Codex prompt fragments for manual merge into `~/.codex/AGENTS.md`; Codex skill trees link from `shared/skills/`.
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

The bundle currently centralizes these non-secret local agent assets:

- Shared skills: `code-hygiene-refactor`, `hygiene-orchestrator`, `type-strictness`, `test-extender`, `requirements-spec`, `implement-spec`, `isx-cli`, `rtk-cli` ([RTK](https://github.com/rtk-ai/rtk); hooks via `rtk init`), `codegraph-cli` ([CodeGraph](https://github.com/colbymchenry/codegraph); MCP via `codegraph install`), and `code-smell-utility-locator`.
- Claude agents/subagents: `agent-python-executor.md` (the canonical Python executor; sometimes referred to as `python-agent-executor`), plus feasibility, requirements, testing-architect, and test-orchestrator agents.
- Claude subagent digests: `python-core.md`, `python-testing.md`, `typescript-core.md`, and `workflow-quality.md`.
- Claude and OpenCode rule shard mirrors under `claude/rules/` and `opencode/rules/`.
- Slopgate-specific prompt fragments from Claude and OpenCode global guidance.

Not centralized: project-specific digests such as Job Hunter context, Cursor generated MCP metadata/transcripts/caches, and live hook files. Those remain project/runtime state, not bundle source.
