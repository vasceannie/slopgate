# Slopgate Hook Recovery (OpenCode fragment)

- Treat enrolled-repo slopgate warnings as hard instructions even when OpenCode only receives advisory context.
- OpenCode hook support is degraded: no prompt interception and Stop is advisory; do not finish while hook context says unresolved quality work remains.
- On a denial/block, read the rule ID, load the smallest matching rule shard, reread the target file, then change design before retrying.
- If the same rule/path fails twice, write a short repair plan before the next write.
- For repeated `PY-CODE-012`, `PY-CODE-013`, `PY-CODE-017`, `PY-CODE-018`, thin-wrapper, feature-envy, duplicate-helper, scattered-utility, or oversized-module failures, load `code-hygiene-refactor` before retrying. If the repair spans many files, switch to `hygiene-orchestrator`.

Merge this fragment into `~/.config/opencode/AGENTS.md`; do not symlink over the full AGENTS.md file.
