# Shell Non-Interactive

- No editors, pagers, REPLs, or prompt-driven commands.
- Prefer explicit flags: `-y`, `--yes`, `--no-edit`, `--non-interactive`.
- Use `CI=true`, `GIT_TERMINAL_PROMPT=0`, `GIT_EDITOR=true`, `GIT_PAGER=cat`, and `PAGER=cat` when needed.
- Prefer native read/edit tools over shell text munging.
- Use timeout or non-interactive piping if a command might hang.
