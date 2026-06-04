# Git Workflow

## Commits

- **Atomic commits**: One logical change per commit
- **Conventional Commits**: `feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`
- **Short first line**: ≤50 chars, imperative mood
- **Secret scan**: Check for `sk-`, `ghp_`, `AIza` before committing

## Branches

- Suggest new branches for high-risk refactors
- Never force-push to shared branches

## Docs

- Update README if build steps, deps, or env vars change

## Banned

- `git stash` — never use to prove failures are pre-existing or to temporarily revert (vibeforcer GIT-003 blocks this)
- `--no-verify` — never bypass git hooks (vibeforcer GIT-001 blocks this)

## Why

Vibeforcer blocks `git stash` (GIT-003) and `--no-verify` (GIT-001). This rule teaches the workflow that doesn't need those escapes.
