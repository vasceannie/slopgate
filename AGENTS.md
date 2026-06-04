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
