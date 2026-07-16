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

## Feedback-loop state

- Baseline and redacted `PY-LOG-002` audit artifacts live under `docs/evidence/`.
- `WORKFLOW-FIRST-WRITE-001` metadata names the normalized target, missing contract fields, rollout posture, and record-command prefix.
- `QUALITY-PROJECTED-LINT-001` records either a projection digest and collector IDs or a `skip_reason`; `QUALITY-LINT-001.projected_lint_parity` compares the later authoritative result.
- Semantic findings expose `semantic_repeat_count` separately from `exact_repeat_count`. `RETRY-BUDGET-001.recovery_status` explains missing, expired, mismatched, or consumed recovery evidence.
- Only a successful full post-tool read after the retry lock counts as reread proof. Prompt keywords and proposed reads do not unlock recovery.
- `slopgate profile show --cwd PATH` inspects the opt-in aggregate profile. `clear` and `reset` remove that profile without deleting trace history or always-on state.

## Operational safety

- **Never print non-JSON to stdout** from `slopgate handle` — platforms parse stdout as JSON
- Debug output goes to trace logs, not stdout
- Keep async job output concise — it surfaces on the agent's next turn
- If slopgate crashes, it exits non-zero and the platform skips the hook (fail-open)
