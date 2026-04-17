# Vibeforcer Repository Guide

This repository owns the `vibeforcer` rule engine itself: installers, adapters,
runtime enforcement, lint detectors, and platform integration shims.

## Scope

- Treat this repo as the source of truth for rule definitions and platform
  capability mapping.
- Do not assume a downstream repository is enrolled in `quality_gate.toml`
  unless that repo or worktree actually contains it.
- When verifying whether a rule would have blocked a change, check the target
  repo or worktree where the violation occurred, not just this rule repo.

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
