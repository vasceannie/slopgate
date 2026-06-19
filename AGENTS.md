# Slopgate — rule engine, installers, adapters, lint detectors.

## Scope

- Source of truth for rule defs / platform capability mapping.
- Bundle shared agent assets under `bundle/`, not scattershot into `~/.claude`.
- `slopgate install` owns harness hook wiring; bundle fragments merge, never symlink over CLAUDE.md.
- Check target repo for `slopgate.toml` enrollment, not just this repo.

## Platform reality

- Claude Code: richest hook surface, nearest full parity.
- Codex: partial hook model; document conservatively.
- OpenCode: plugin/event translation, not Claude-style schema.

## Docs

- Keep README aligned with upstream docs; prefer "partial"/"best-effort" over parity claims.

<!-- gitnexus:start -->
**GitNexus:** `slopgate` indexed (18733 symbols). Always run `gitnexus_impact` before editing any symbol. Run `gitnexus_detect_changes()` before committing. See skills in `.claude/skills/gitnexus/` for CLI-by-task mapping.
<!-- gitnexus:end -->
