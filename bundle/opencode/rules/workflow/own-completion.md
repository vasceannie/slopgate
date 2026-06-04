# Ownership & Completion

Enforcer hooks block the worst violations at edit time. These rules ensure you write it right the first time.

## Do This

- **Fix-First**: Warnings/errors in touched files or nearby subsystems — fix them, don't prove they pre-date your change
- **Ownership Presumption**: Issues in modified files or their dependency chain are yours to resolve, explicitly defer, or escalate
- **Deferral Requires Justification**: "Pre-existing" or "out of scope" alone is insufficient — state why fixing now would expand scope or risk regression
- **Completion Standard**: Don't mark work complete while touched/adjacent issues remain unresolved without a deferral note
- **Token Efficiency**: One targeted validation + remediation beats multi-step attempts to prove innocence
- **Boy Scout Rule**: Leave code cleaner than you found it — fix adjacent lint/type issues in files you touch

## Not This

- Running `git stash` or `git diff` to prove a failure predates your change
- Marking a task complete with unresolved warnings in modified files
- Deferring without stating the risk of fixing now

## Why

Slopgate (STOP-001) blocks dismissing pre-existing issues. This rule teaches the mindset so you don't hit the block at all.

## PostToolUse Repair Ownership

- A PostToolUse block means the previous edit may have landed; inspect and repair before proceeding.
- `STOP-001`/`STOP-002`: do not finish by arguing an issue was pre-existing. Fix touched-file issues or state a concrete risk-based deferral.
- On repeated denies, stop feature work and write a repair plan with target path, violated rule IDs, and one verification command.
