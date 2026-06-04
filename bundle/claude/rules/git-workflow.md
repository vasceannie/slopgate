# Git Workflow

- Atomic commits: one logical change each. Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`). First line ≤50 chars, imperative.
- Secret scan before committing: `sk-`, `ghp_`, `AIza`.
- New branches for high-risk refactors. Never force-push to shared branches.
- Update README if build steps, deps, or env vars changed.

## Banned

- `git stash` (GIT-003) — never to prove "pre-existing" or temporarily revert.
- `--no-verify` (GIT-001) — never bypass git hooks.
