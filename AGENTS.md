# Slopgate Repository Guide

This repository owns the `slopgate` rule engine itself: installers, adapters,
runtime enforcement, lint detectors, and platform integration shims.

## Scope

- Treat this repo as the source of truth for rule definitions and platform
  capability mapping.
- Do not assume a downstream repository is enrolled in `slopgate.toml`
  unless that repo or worktree actually contains it.
- When verifying whether a rule would have blocked a change, check the target
  repo or worktree where the violation occurred, not just this rule repo.
- Harness-facing agent assets belong under `bundle/` when they are meant to be
  shared or packaged: skills, prompt fragments, rule shards, Claude agents, and
  MCP templates. Do not scatter Slopgate-branded skills/rules back into
  `~/.claude` or `~/.config/opencode` except via the manifest-driven symlinks.
- `slopgate install` remains the sole owner of live harness hook wiring
  (`hooks.json`, Claude `settings.json` hook entries, and the OpenCode plugin
  install target). Bundle prompt fragments must be merged/imported; never
  symlink over full `CLAUDE.md` or `AGENTS.md` files.

## Platform reality

- Claude Code has the richest hook surface and is the closest thing to full
  runtime parity.
- Codex support is partial. Its hook model is more limited than Claude Code
  and should be documented conservatively.
- OpenCode support is implemented through plugins and event translation, not a
  Claude-style hook schema. Document capability differences explicitly.

## Documentation bar

- Keep README claims aligned with current upstream platform docs.
- Prefer "partial" or "best-effort" wording over parity claims unless the
  upstream docs clearly support them.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **slopgate** (14579 symbols, 25786 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/slopgate/context` | Codebase overview, check index freshness |
| `gitnexus://repo/slopgate/clusters` | All functional areas |
| `gitnexus://repo/slopgate/processes` | All execution flows |
| `gitnexus://repo/slopgate/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
