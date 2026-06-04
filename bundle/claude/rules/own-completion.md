# Ownership & Completion

Hook STOP-001/002 blocks dismissing pre-existing issues. Write code so it doesn't fire.

- **Fix-first:** warnings/errors in touched files or nearby subsystems — fix them, don't prove they predate the change.
- **Ownership:** issues in modified files or their dependency chain are yours to resolve, explicitly defer (with risk-based reason), or escalate.
- **Deferral needs justification:** "pre-existing" alone is insufficient — state why fixing now expands scope or risks regression.
- **Boy Scout:** fix adjacent lint/type issues in files you touch.
- **Don't** run `git stash`/`git diff` to argue innocence, or mark work complete with unresolved touched-file issues.

## PostToolUse repairs

- A PostToolUse block means the previous edit may have landed; inspect and repair.
- Repeated denies → stop feature work, write a repair plan with target path, violated rule IDs, one verification command.
