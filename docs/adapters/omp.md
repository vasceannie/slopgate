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
- Counters reset on `input`, on `session_switch` / `session_branch` / `session_tree` navigation, on
  clean/advisory settle, on active-stop-hook settle, and on cap exhaustion. A repeated
  `session_start` for a live session does not reset the counter.

## Native plugin registration

`slopgate install omp` stages a Slopgate-owned local marketplace (`slopgate-runtime`) under
Slopgate's user data directory (`<user data>/slopgate/native/omp/marketplace`, catalog in
`.omp-plugin/marketplace.json`, an immutable payload snapshot per content digest) and registers
`omp-slopgate@slopgate-runtime` with `omp plugin install --scope user|project`. Inspect it with
`omp plugin list --json`. The plugin version is `<slopgate version>+local.<digest>`, so a version
bump gets a fresh snapshot even when the rendered extension is byte-identical; reinstalling the
same content runs no native command. Replacing a changed payload uses `omp plugin install --force`,
which keeps native enabled/disabled state: a disabled plugin is reported as registered but not
active and is never silently enabled.

Project scope runs OMP with the requested project root as its working directory. If OMP would
anchor the project on an ancestor repository, the install is refused with both paths named. A
missing `<project>/.omp` is created empty only during a real install and removed again on rollback.

Legacy loose copies (`$PI_CODING_AGENT_DIR/extensions/omp-slopgate/` when `PI_CODING_AGENT_DIR` is
absolute, else `~/.omp/agent/extensions/omp-slopgate/`, and `<project>/.omp/extensions/omp-slopgate/`)
are recognized by their Slopgate ownership markers. They are backed up and removed only after the
native registration for that scope is verified, so exactly one copy stays active. Unknown files,
malformed ownership metadata or paths escaping the install root make the install fail before any
native command runs. If the `omp` CLI is missing the install fails and legacy enforcement is left
intact. Any later failure rolls back staging, native registrations and legacy files.

`slopgate uninstall omp` honors `--install-scope` and `--project-root`: it removes only the
selected scope's registration plus recognized legacy files, and keeps the marketplace and staged
payload because another scope or project may still use them. `--dry-run` prints the exact native
commands and changes nothing. Start a new OMP session after installing. Profile-specific roots
(`~/.omp/profiles/<profile>/...`) are not handled yet.

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
- **Edit protection is target-path only.** The bridge parses OMP's native edit
  envelopes (bracket hashline headers and `apply_patch` file headers, including
  payloads dispatched under the internal `edit` tool name) and blocks protected
  targets before execution. Policy evaluation on the projected post-edit file
  content — OpenCode's projection behavior — is not implemented for Pi or OMP.
- **Black-box omp-executable smoke is deferred.** Launching a pinned real `omp` binary with a fake
  deterministic enforcer is not part of this wave; the harness proves the contract through OMP's real
  `ExtensionRunner` instead.
- **`slopgate test` does not auto-discover the OMP harness** (`js_ts_tests.py:30-42`); the Bun suite
  runs from `tests/runtime/omp/` only.
- **Profiles, the CI drift lane, and dashboard harness status are deferred.** Profile-specific install
  roots are not installed, the latest-OMP conformance lane is not wired into CI, and dashboard
  harness-status probing remains out of scope (see Dashboard deferrals).
- **Pi failure discrimination fix (FK2=B).** As part of this work, `PiAdapter.normalize_payload` was
  corrected to classify failed `tool_result` events into `PostToolUseFailure` from the bridge's
  top-level `isError` and `details.exitCode`/`exit_code` fields (the bridge no longer nests the
  whole event as `pi_event`, and `tool_execution_end` is notification-only and not enforced).
  OMP's `tool_result` + `isError` split follows the same pattern. The Pi and OMP bridges deliver
  post-tool findings through the native `tool_result` content patch and add routine session/prompt
  context to the per-request system prompt rather than persisting a custom conversation message.

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
