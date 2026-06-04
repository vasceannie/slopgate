# Archived: `windows-powershell-compat` worktree

The directory `slopgate-windows-powershell/` was a **git worktree** on branch
`windows-powershell-compat`, used to experiment with PowerShell-friendly hook
install paths and a consolidated `installer.py` layout.

## Status: archived (2026-06)

That branch is **obsolete**. Native Windows support (PowerShell launcher, `%APPDATA%`
config, Codex/OpenCode install paths) lives in the main **slopgate** tree on `master`.

Do not develop against `windows-powershell-compat`. Use:

```bash
cd ~/.openclaw/workspace-hooker/slopgate
uv tool install .
slopgate install claude   # or install all
slopgate test
```

## Preserving history

Before removing the worktree, the tip commit was tagged:

```bash
git tag -a archive/windows-powershell-compat <tip-sha> -m "Archive windows-powershell-compat worktree"
```

To inspect the old branch without a checkout:

```bash
git show archive/windows-powershell-compat
git log archive/windows-powershell-compat --oneline -10
```

## Removing the worktree (one-time)

From the slopgate repo root:

```bash
./scripts/remove_windows_powershell_worktree.sh
```

Or manually:

```bash
git worktree remove ../slopgate-windows-powershell
git branch -d windows-powershell-compat   # optional after tag exists
```
