# Remote proxy-server use case

This note records the Slopgate changes retained while moving the working branch to
`main` and synchronizing with the upstream source.

## Synchronization state

- Local branch: `main`
- Upstream source remote: `github`
- Mirror/deployment remote: `origin`
- Current synchronized commit: `1f8f9ad` (`v2.0.0`)
- The remotes currently publish `master`; the local `main` branch tracks
  `origin/master` until the remotes are renamed server-side.
- The latest fetch showed no commits to merge from `github/master`.

## Alterations retained for the proxy use case

These are first-party Slopgate changes in the daemon and hook path, rather than
upstream configuration assumptions:

1. **Resident daemon transport.** `slopgate daemon [--socket PATH]
   [--max-requests N] [--workers N | --serial]` evaluates hook requests over a
   newline-framed JSON protocol on a Unix-domain socket. Socket discovery prefers
   `$XDG_RUNTIME_DIR/slopgate-hookd.sock`, then a user-scoped temporary socket.
   Frames are capped at 1 MiB and non-socket paths are never unlinked.
2. **Installed POSIX hook proxy.** POSIX hook commands buffer stdin, try a small
   Node.js socket client first, and preserve the original Slopgate command as the
   direct fallback. Empty stdin remains a no-op.
3. **Admission-aware failure behavior.** A connection failure or failure before
   daemon admission returns the fallback sentinel. Once the daemon has accepted a
   request, timeout, malformed response, or daemon error fails closed instead of
   running the request a second time locally.
4. **Project-aware concurrency.** The daemon can use multiple workers while
   serializing requests for the same repository and allowing independent
   repositories to make progress concurrently. `--serial` remains available for
   conservative deployments.
5. **Provenance and telemetry context.** Requests carry platform/event metadata;
   missing platform information is reported as `unknown`, not guessed as Claude.
   The daemon path also preserves the existing Slopgate output and exit-code
   contract for the calling harness.
6. **Operational controls.** The daemon exposes `--socket`, `--max-requests`,
   `--workers`, and `--serial`; the installed hook proxy uses the shared 30-second
   client timeout and a distinct pre-admission fallback sentinel.

The related implementation and regression coverage live in:

- `src/slopgate/daemon/`
- `src/slopgate/installer/hook_proxy.py`
- `src/slopgate/cli/hook_runtime.py`
- `tests/test_installer_daemon_proxy.py`

## Remote-server boundary

The current implementation is **same-host daemon forwarding**, not a network
proxy. The hook process and `slopgate daemon` must be able to reach the same Unix
socket. It does not provide a TCP/HTTP transport, authentication, encryption, or
automatic SSH forwarding to a daemon on another machine.

For a genuinely remote proxy server, add or deploy a separately reviewed
transport layer (for example, an authenticated SSH tunnel or a mutually
authenticated HTTP/gRPC adapter) rather than pointing the Unix-socket path at a
network address. Preserve the admission-aware failure contract: never retry a
request locally after the remote service has accepted it.

## Verification

The proxy behavior is covered by tests for:

- Node-client success and accepted failure responses;
- pre-admission socket failure and fallback behavior;
- accepted timeout fail-closed behavior;
- missing platform provenance;
- shell-command generation and fallback argv preservation; and
- Windows retaining its direct PowerShell hook path.
