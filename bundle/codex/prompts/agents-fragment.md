# Slopgate Codex prompt fragment

- Treat slopgate hook output as binding when Codex receives a block, stopReason, or additionalContext from `slopgate handle --platform codex`.
- Codex hooks are GA but still have platform-specific coverage gaps. Preview changes with `slopgate install codex --install-scope user --dry-run`, refresh them with `slopgate install codex`, then run `/hooks` in Codex to review and trust the installed definitions.
- Run `slopgate lint check` from the repository root for quality verification; do not pass file/path arguments.

Manually merge this fragment into `~/.codex/AGENTS.md` when desired. Do not symlink over the full AGENTS.md file.
