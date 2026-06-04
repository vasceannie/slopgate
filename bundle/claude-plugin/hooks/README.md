# Slopgate hook installation

This Claude plugin intentionally does **not** ship production hook commands.

Install live Claude hooks with the CLI instead:

```bash
slopgate install claude
# or, for all detected harnesses on the current device
slopgate install all
```

Reason: `slopgate install` owns `~/.claude/settings.json`, `.claude/settings.json`, and other harness `hooks.json`/plugin surfaces so it can preserve user hooks, create backups, merge safely, and use the correct local `slopgate` binary path.
