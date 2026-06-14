# OpenCode Daemon And Trace Findings

## Summary

Codex is not the only harness being logged. It only looks that way when tailing the
latest Slopgate JSONL files because the current Codex session started after the
last observed OpenCode activity and every diagnostic shell command in this
investigation is itself traced as Codex.

OpenCode is being acknowledged by the running server at `localhost:4096` and is
forwarding events into Slopgate. The remaining operational caveat is daemon
routing: the OpenCode web process does not currently expose the same daemon
socket environment as the resident Slopgate daemon process, so OpenCode can log
events while still bypassing the resident daemon and falling back to direct
`slopgate handle --platform opencode` evaluation.

## Evidence

- Slopgate's active trace directory is `/home/trav/.config/slopgate/logs`.
- Full trace counts in `events.jsonl` show all harnesses, not just Codex:
  - `opencode`: 73,505 events
  - `claude`: 64,193 events
  - `codex`: 29,929 events
  - `cursor`: 17,447 events
  - `unknown`: 2,839 events
- Same-day counts since `2026-06-14T00:00:00Z` show OpenCode is the largest
  source for the day:
  - `opencode`: 15,790 events
  - `claude`: 9,945 events
  - `codex`: 3,155 events
  - `unknown`: 5 events
- Latest OpenCode traces before this investigation were at
  `2026-06-14T08:40:58Z`. The current Codex session began writing new trace
  entries at `2026-06-14T08:44:47Z`, which explains the Codex-only tail.
- The latest OpenCode records are real plugin traffic, not replay noise:
  - session id: `opencode-1781419828043-sm37zd`
  - cwd: `/home/trav/repos/job-hunter`
  - native events: `session.status`, `session.idle`, `tool.execute.before`,
    and `tool.execute.after`
  - sampled tool: `background_output`
- Between `2026-06-14T06:50:00Z` and `2026-06-14T08:41:00Z`, OpenCode emitted:
  - `session.status`: 1,904
  - `tool.execute.before`: 1,481
  - `tool.execute.after`: 1,427
  - `file.edited`: 67
  - `session.idle`: 57
  - `session.created`: 18
  - `session.compacted`: 8
  - `command.executed`: 3
  - `session.error`: 1
- `http://localhost:4096/` responded with the OpenCode web app, and
  `http://localhost:4096/event` responded with an SSE `server.connected` event.
- The active OpenCode server config exposed by `http://localhost:4096/config`
  includes `file:///home/trav/.config/opencode/plugins/slopgate-plugin.ts`.
  Do not rely only on `/home/trav/.config/opencode/opencode.json` for this,
  because that static file did not list the Slopgate plugin while the running
  merged server config did.
- OpenCode's own log at `/home/trav/.local/share/opencode/log/opencode.log`
  records Slopgate plugin load messages for the current server run, including:
  - `2026-06-14T06:50:28Z`, session `opencode-1781419828043-sm37zd`
  - `2026-06-14T06:52:19Z`, session `opencode-1781419938785-zb3jf8`

## Daemon Check

The resident daemon is running and the daemon itself accepts OpenCode-shaped
requests:

- live daemon socket tested: `/run/user/1000/slopgate-hookd.sock`
- smoke payload:
  - platform: `opencode`
  - native event: `session.status`
  - session id: `opencode-daemon-smoke`
- daemon response:
  - `ok=True`
  - `accepted=True`
  - `exit_code=0`
  - `output={}`
- trace confirmation:
  - `events.jsonl` recorded platform `opencode`, event `SessionStatus`,
    platform event `session.status`, session `opencode-daemon-smoke`
  - `results.jsonl` recorded the same event with no findings and no rendered
    output, which is expected for a no-op advisory lifecycle event

That proves the resident daemon can acknowledge OpenCode requests when the
request reaches the daemon socket.

## Routing Finding

The OpenCode server process at `localhost:4096` does not currently show either
`SLOPGATE_DAEMON_SOCKET` or `XDG_RUNTIME_DIR` in its environment. The resident
daemon process does have `XDG_RUNTIME_DIR=/run/user/1000`, which makes its
default socket `/run/user/1000/slopgate-hookd.sock`.

Because `src/slopgate/cli/hook_runtime.py` only chooses the daemon for
`slopgate handle` when `SLOPGATE_DAEMON_SOCKET` is set or the process-local
default socket exists, OpenCode's plugin can successfully log events while still
not using the resident daemon. With the observed OpenCode environment, the
process-local default resolves to `/tmp/slopgate-hookd-1000.sock`, which did not
exist during this check.

This is not a missing OpenCode acknowledgement bug. It is an environment-routing
gap if the operator expects the OpenCode server to use the resident daemon.

## Operational Guidance

- For dashboards and log triage, filter by `platform` and use a time window. Do
  not infer harness coverage from the newest tail after Codex has started
  running diagnostics.
- For OpenCode server acknowledgement, check both:
  - active server config from `http://localhost:4096/config`, with sensitive
    provider settings redacted before sharing
  - Slopgate JSONL traces for `platform="opencode"` and `session_id` values
    beginning with `opencode-`
- For daemon-backed OpenCode handling, launch the OpenCode service with an
  explicit daemon socket, preferably per repo or per service:
  - `SLOPGATE_DAEMON_SOCKET=/run/user/1000/slopgate-hookd.sock` for the current
    live socket
  - or a repo-specific socket such as `/run/user/1000/slopgate-job-hunter.sock`
    when multiple repos are active
- If the OpenCode service is intentionally shared across repos, direct CLI
  fallback may be safer than a shared daemon socket unless repo-specific routing
  is configured.

## Conclusion

OpenCode events from the running `localhost:4096` server are being forwarded and
recorded. The apparent Codex-only logging is a tailing artifact caused by current
Codex diagnostics after OpenCode went idle at `2026-06-14T08:40:58Z`.

The piece to fix operationally is not OpenCode event acknowledgement; it is
service environment propagation if OpenCode should use the resident Slopgate
daemon instead of direct `slopgate handle --platform opencode` fallback.
