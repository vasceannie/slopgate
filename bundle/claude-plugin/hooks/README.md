# Slopgate hook installation

This Claude plugin intentionally does **not** ship production hook commands.

Install live Claude hooks with the CLI instead:

```bash
slopgate install claude --install-scope user
# or, for all detected harnesses on the current device
slopgate install all --disable-autoupdate
# preview either command without writing files
slopgate install claude --install-scope project --project-root /path/to/repo --dry-run
```

Reason: `slopgate install` owns `~/.claude/settings.json`, `.claude/settings.json`, and other harness `hooks.json`/plugin surfaces so it can preserve user hooks, create backups, merge safely, and use the correct local `slopgate` binary path.
