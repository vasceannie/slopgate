# Slopgate Codex prompt fragment

- Treat slopgate hook output as binding when Codex receives a block, stopReason, or additionalContext from `slopgate handle --platform codex`.
- Codex hook support is partial; verify hook-related edits with `slopgate install codex --dry-run` and `slopgate test` instead of assuming Claude parity.
- Run `slopgate lint check` from the repository root for quality verification; do not pass file/path arguments.

Manually merge this fragment into `~/.codex/AGENTS.md` when desired. Do not symlink over the full AGENTS.md file.
