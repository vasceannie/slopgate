# Debugging and Replay

## Log files

slopgate writes JSONL logs to `~/.config/slopgate/logs/` (or the configured trace directory):

| File | Contents |
|---|---|
| `events.jsonl` | Event summaries (platform, event, tool, paths, languages) |
| `rules.jsonl` | Per-rule matches with severity, decision, message, metadata |
| `results.jsonl` | Final rendered output + all findings + errors |
| `subprocess.jsonl` | Synchronous subprocess runs (post-edit quality) |
| `async/subprocess.jsonl` | Async post-edit job runs |

## Quick analysis

```bash
# Activity summary (last 24 hours)
slopgate stats --days 1

# JSON output for scripts
slopgate stats --days 7 --json

# Custom log path
slopgate stats --log /path/to/results.jsonl
```

## Replay a fixture or captured payload

```bash
# Replay a bundled fixture
slopgate replay --payload fixtures/pretool_git_no_verify.json --pretty

# Replay with a specific platform adapter
slopgate replay --payload /tmp/captured.json --platform codex --pretty
```

## Capture a live payload

To capture what a platform sends, temporarily wrap the hook:

```bash
# In settings.json, replace:
#   "command": "slopgate handle"
# With:
#   "command": "tee /tmp/hook_capture.json | slopgate handle"
```

Then replay:

```bash
slopgate replay --payload /tmp/hook_capture.json --pretty
```

## Common debugging workflow

1. Reproduce the issue (trigger the hook)
2. Check `slopgate stats --days 1` for the event
3. Inspect `results.jsonl` for the specific evaluation
4. Replay the payload to confirm behavior
5. Decide where the fix belongs:
   - **config** — regex rules, protected paths, thresholds
   - **Python rule** — complex logic, AST, subprocess
   - **adapter** — platform-specific normalization

## False positive checklist

- Path glob too broad? → narrow `path_globs` or add `exclude_path_globs`
- Rule should be repo-configurable? → use `slopgate.toml` overrides
- Content rule fires on read-only tools? → check `events` list
- Shell command detector too broad? → add to `SAFE_READ_SHELL_VERBS`
- Protected path catches legitimate edits? → adjust `protected_paths` in config

## False negative checklist

- Payload extractor missing a tool field variant? → update `payloads.py`
- Patch paths not being surfaced? → check `parse_patch_candidate_paths()`
- File should be re-read after PostToolUse? → ensure rule reads from disk
- Rule missing from `PermissionRequest` events? → add to `events` tuple
- Need richer analysis? → write a Python rule (AST, subprocess, etc.)

## Operational safety

- **Never print non-JSON to stdout** from `slopgate handle` — platforms parse stdout as JSON
- Debug output goes to trace logs, not stdout
- Keep async job output concise — it surfaces on the agent's next turn
- If slopgate crashes, it exits non-zero and the platform skips the hook (fail-open)
