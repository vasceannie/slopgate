# Cutover from Enforcer

## What changes

| Before (enforcer) | After (slopgate) |
|---|---|
| `~/.claude/hooks/enforcer/` (install root) | `~/.config/slopgate/` (config) + binary on PATH |
| 14 shell wrappers (`.claude/hooks/*.sh`) | `slopgate handle` called directly |
| `CLAUDE_HOOK_LAYER_ROOT` env var | `SLOPGATE_ROOT` / `SLOPGATE_CONFIG` (optional) |
| `hook-layer` entry point | `slopgate` entry point |
| `config.json` at `.claude/hook-layer/config.json` | `config.json` at `~/.config/slopgate/config.json` |
| Separate `hook-stats.py` script | `slopgate stats` |
| Per-platform install scripts | `slopgate install <platform>` |
| Manual settings.json patching | Automatic via `slopgate install claude` |

## What stays the same

- All bundled Python hook rules (42: 3 always-on + 39 repo-strict) — identical behavior
- All 45 bundled regex rules — loaded from same config format
- Adapter core behavior is shared, but platform hook capabilities differ
  (Claude has fullest parity; Codex/OpenCode have platform-specific limits)
- `slopgate.toml` per-repo overrides — identical
- JSONL trace format — identical
- Fixture format — identical

## Step-by-step cutover

### 1. Install slopgate globally

```bash
# From the slopgate source directory
uv tool install .

# Verify
slopgate version
slopgate test
```

PowerShell:

```powershell
# From the slopgate source directory
uv tool install .

slopgate version
slopgate test
```

### 2. Initialize config

```bash
# Create ~/.config/slopgate/ with default config
slopgate config init

# Or copy your existing enforcer config
mkdir -p ~/.config/slopgate/logs/async
cp ~/.claude/hooks/enforcer/.claude/hook-layer/config.json ~/.config/slopgate/
```

If copying your existing config, update `prompt_context_files` paths:
```json
"prompt_context_files": [
    "prompt_context/organization.md",
    "prompt_context/repo.md"
]
```

And copy prompt context:
```bash
cp -r ~/.claude/hooks/enforcer/.claude/hook-layer/prompt_context ~/.config/slopgate/
```

On native Windows, `slopgate config init` writes to
`%APPDATA%\slopgate\config.json` unless `SLOPGATE_CONFIG_DIR` is set.

### 3. Install platform hooks

```bash
# Preview what will change
slopgate install claude --dry-run

# Apply — replaces shell wrapper references with direct slopgate call
slopgate install claude
```

This patches `~/.claude/settings.json` to call `slopgate handle` for all hook events, replacing the old shell wrapper paths.

For Codex:
```bash
slopgate install codex
```

For OpenCode:
```bash
slopgate install opencode
```

Native Windows hook commands are emitted through a PowerShell-compatible
launcher so installed console scripts under `AppData` can be called even when
their path contains spaces. `slopgate install opencode` writes the plugin to
`%APPDATA%\opencode\plugins\slopgate-plugin.ts` and embeds the discovered
binary path with JSON/TypeScript-safe escaping; set `SLOPGATE_BIN` to override
it at runtime. Codex CLI hook availability on native Windows still
depends on the installed Codex version; if Codex does not run hooks on Windows,
use WSL or Git Bash for runtime enforcement.

### 4. Verify

```bash
# Self-test
slopgate test

# Check that stats still work (reads from legacy log location if XDG doesn't exist yet)
slopgate stats --days 1

# Test a real hook invocation
echo '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"git commit --no-verify"},"cwd":"/tmp","session_id":"cutover-test"}' | slopgate handle
```

### 5. Clean up (optional)

Once you're confident slopgate is working:

```bash
# Remove old shell wrappers and enforcer installation
# (keep for a while as backup if you prefer)
rm -rf ~/.claude/hooks/enforcer
```

## Rollback

If something breaks:

```bash
# Restore enforcer by re-running its install
cd ~/.claude/hooks/enforcer
bash scripts/install.sh

# Or manually restore settings.json from backup
# (slopgate install doesn't delete the old settings, just overwrites hooks)
```

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `SLOPGATE_CONFIG` | Explicit config file path | (discovery chain) |
| `SLOPGATE_CONFIG_DIR` | Config directory override | `~/.config/slopgate` |
| `SLOPGATE_ROOT` | Root for traces/prompt context | config dir |
| `CLAUDE_HOOK_LAYER_ROOT` | Legacy fallback (backward compat) | — |
