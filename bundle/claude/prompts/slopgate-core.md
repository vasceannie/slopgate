# Slopgate core guidance fragment

Slopgate hooks block quality violations at edit time. Config: `~/.config/slopgate/`. CLI: `slopgate` (short: `sgt`). Rules in `~/.claude/rules/` are path-scoped; load the smallest matching shard before risky edits.

## Hook denial recovery

- Hook IDs are routing keys. Load the matching rule shard before retrying.
- PreToolUse denies prevented the mutation. PostToolUse denies mean the edit landed; reread and repair.
- Same rule/path denied twice means stop and write a three-bullet repair plan before the next write.
- Bundled recovery skills: `code-hygiene-refactor` for PY-CODE-012/013/017/018 and similar design smells, `hygiene-orchestrator` for broad QUALITY-LINT batches, `isx-cli` for semantic search, and `code-smell-utility-locator` before adding new helpers/wrappers.

Import this fragment from `~/.claude/CLAUDE.md` or a project CLAUDE.md with an `@path/to/bundle/claude/prompts/slopgate-core.md` line. Do not replace the whole user CLAUDE.md with this file.
