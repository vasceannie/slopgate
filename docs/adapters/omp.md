# OMP adapter

OMP is registered in Slopgate's installer, suite discovery, CLI platform registry,
and dashboard trace surfaces. Dashboard harness-status probing remains deferred
until OMP exposes a stable status contract.

## Event map

OmpAdapter normalizes the OMP-native lifecycle into Slopgate's canonical events:

| OMP event | Canonical event |
|---|---|
| `session_start` | `SessionStart` |
| `input` | `UserPromptSubmit` |
| `tool_call` | `PreToolUse` |
| `user_bash` / `user_python` | `PreToolUse` (mapped to `Bash` / `Python`) |
| `tool_result` (`isError` false) | `PostToolUse` |
| `tool_result` (`isError` true) | `PostToolUseFailure` |
| `session_stop` | `Stop` |
| `turn_end` | `TurnEnd` |
| `agent_end`, `tool_execution_start/update/end`, `message_*`, session lifecycle, and other observability events | Telemetry only; no canonical event |

45 raw event names are aliased (`_OMP_EVENT_ALIASES`), and only the enforcement-relevant subset
renders output. Rendering happens at the Slopgate CLI seam with no `action` protocol: deny
`{block, reason}`, rewrite `{updated_input}`, prompt deny `{handled, reason}`, stop continuation
`{continue, additionalContext}`, and post-tool `tool_result_patch` details. `SessionStart` and
advisory events emit `{context}`.

## session_stop continuation

`session_stop` is OMP's main-session stop hook, executed before a turn settles. Findings render as
`{ continue: true, additionalContext }` so the agent gets another pass with repair guidance.

- Continuations are counted per session id, keyed by `ctx.sessionManager.getSessionId()` or the
  deterministic `SLOPGATE_SESSION_ID` override.
- The per-session cap is 8 (`MAX_STOP_CONTINUATIONS`); hitting it resets the counter and posts a
  cap notice instead of continuing.
- OMP's `stop_hook_active` input flag means OMP already has a stop hook active: Slopgate resets
  the counter and stays advisory-only, preventing continuation loops.
- Counters reset on `session_start`, on `input`, on clean/advisory settle, on active-stop-hook
  settle, and on cap exhaustion.

## Install sites and resolver

| Scope | Path |
|---|---|
| User | `$PI_CODING_AGENT_DIR/extensions/omp-slopgate/index.ts` when `PI_CODING_AGENT_DIR` is absolute, else `~/.omp/agent/extensions/omp-slopgate/index.ts` |
| Project | `<project>/.omp/extensions/omp-slopgate/index.ts` |

Each site holds two Slopgate-owned artifacts: `index.ts` and the canonical `package.json` manifest.
Install snapshots both with file bytes, modes, and missing directories, refuses to replace
unrecognized files, and rolls back every completed site when any step fails. Uninstall removes
owned artifacts and the leftover extension directory. `slopgate install omp` / `slopgate uninstall
omp` honor `--install-scope` and `--project-root` like the other platforms. Profile-specific roots
(`~/.omp/profiles/<profile>/...`) are not installed yet.

## Harness usage

The pinned contract harness lives in `tests/runtime/omp/`. Run it explicitly:

```
cd tests/runtime/omp && bun install && bun run test
```

- Use `bun run test`, not `bun test`: the `pretest` script stages the production-rendered bridge first.
- The staging guard renders `omp_extension.ts` through the production Python renderer twice and
  requires byte-identical output; the staged/source diff must be exactly the `__SLOPGATE_BIN__`
  placeholder line.
- Capture to promote: `bun run capture` writes two deterministic captures under
  `tests/fixtures/omp/.capture/`, byte-compares them, then `bun run scripts/promote-capture.ts`
  promotes after review. Determinism comes from the fixed `SLOPGATE_SESSION_ID`, literal
  `"cwd": "."`, and fixed tool-call IDs. See Captured envelope regeneration below for the full flow.
- Pin-bump policy: moving the `@oh-my-pi/pi-coding-agent` pin is a deliberate change. Fixtures stay
  immutable until reviewed against the new pin and contract snapshot; the CI drift lane against
  latest OMP remains a separate deferred lane.

## Known limitations

- **SubagentStop rules are unenforceable.** OMP's `session_stop` is the main-session stop hook and
  does not run for task or subagent sessions, so subagent-stop findings cannot request a continuation.
- **Tool-input rewrite is bash-only and off by default.** The bridge rewrites only proven Bash inputs
  (`command`, `cwd`, `async`, `pty`, `timeout`, `env`) and only when `SLOPGATE_OMP_INPUT_REWRITE=1`
  is set. OMP's normalized event input can carry gate-only derived fields that differ from the raw
  execution parameters, so rewriting the normalized shape risks approving or executing something other
  than what was reviewed. Per-tool raw-parameter reconstruction is a follow-up.
- **Black-box omp-executable smoke is deferred.** Launching a pinned real `omp` binary with a fake
  deterministic enforcer is not part of this wave; the harness proves the contract through OMP's real
  `ExtensionRunner` instead.
- **`slopgate test` does not auto-discover the OMP harness** (`js_ts_tests.py:30-42`); the Bun suite
  runs from `tests/runtime/omp/` only.
- **Profiles, the CI drift lane, and dashboard harness status are deferred.** Profile-specific install
  roots are not installed, the latest-OMP conformance lane is not wired into CI, and dashboard
  harness-status probing remains out of scope (see Dashboard deferrals).
- **Pi failure discrimination fix (FK2=B).** As part of this work, `PiAdapter.normalize_payload` was
  corrected to classify failed post-execution events into `PostToolUseFailure` from real bridge
  envelopes, inspecting both top-level fields and the nested `pi_event` envelope. OMP's
  `tool_result` + `isError` split follows the same pattern.

## Captured envelope regeneration

The JSON envelopes under `tests/fixtures/omp/18.0.5/` are read-only promoted artifacts from the pinned runtime harness.
Never hand-edit them. From `tests/runtime/omp/`, run `bun run capture` to create and byte-compare two deterministic
captures under `tests/fixtures/omp/.capture/`. After reviewing the capture with the matching pin and contract snapshot,
promote it with `bun run scripts/promote-capture.ts`, rerun the runtime and Python fixture suites, and remove `.capture/`.

## Dashboard deferrals

| Selector | Status | Reason |
|---|---|---|
| `HarnessPlatformStatus.id` | Deferred | The dashboard status response does not yet model OMP. |
| `dashboard/scripts/forcedash_server/remote_scripts/harness_status.py.txt` | Deferred | Remote OMP harness discovery is not part of Todo 5. |
