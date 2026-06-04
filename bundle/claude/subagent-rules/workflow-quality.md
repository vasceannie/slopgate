# Workflow & Quality Standards (subagent digest)
# Source of truth: ~/.claude/rules/ (git-workflow, own-completion, tool-atomic-edits, search-navigation)

## Git
- Atomic commits: one logical change each
- Conventional Commits: feat:, fix:, chore:, refactor:, test:, docs:
- Short first line ≤50 chars, imperative mood
- Secret scan before commit: check for sk-, ghp_, AIza
- NEVER: git stash, --no-verify, force-push to shared branches

## Ownership
- Fix warnings/errors in files you touch — don't relabel them as someone else's mess
- If repair is unsafe for this task, leave a STOP-safe deferral envelope:
  `Deferred follow-up: <rule/path>; reason fixing now expands scope or risks regression; validation/follow-up owner: <person|card|command>`
- Don't mark work complete with unresolved issues in modified files unless the deferral envelope names the follow-up
- Boy Scout Rule: leave code cleaner than you found it

## Edits
- Batch imports + usage in the same edit — formatter deletes "unused" imports between edits
- Prefer edit_file over str_replace or full file writes
- For str_replace: use parallel tool calls for import + code in same file

## Search
- Use `rtk rg` (ripgrep), never `grep` or `rtk grep` for ripgrep-style flags (`--type`, `-t`, `-g`)
- Search before writing: check for existing patterns, exceptions, validators
- Read files with line ranges for >300 lines; summarize large diffs
