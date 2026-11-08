# Harness versions

Agent harnesses (Claude Code, OMP, Pi, OpenCode) release too often to pin in
tests, so nothing here gates on an exact harness version.

- **Native smoke** (`tests/runtime/scripts/verify-installed-artifacts.py`) runs
  against whatever Claude Code, OMP and Pi are installed, and prints the versions
  it ran against. A newer harness is never a failure by itself; only broken
  behavior is.
- **Runtime runners** (the `omp` and `pi` packages under `tests/runtime/*/node_modules`)
  follow their lockfiles. The smoke prints their versions and fails only when a
  runner is not installed.

## Runtime harnesses in CI

The Bun harnesses in `tests/runtime/omp` and `tests/runtime/pi` run in two lanes:

| Job | Runners | Gating |
|---|---|---|
| `runtime-harness` | the exact versions in each `package.json` and `bun.lock` (`bun install --frozen-lockfile`) | Required on every pipeline. Deterministic, so unrelated changes never fail on upstream movement. |
| `runtime-canary` | the registry `latest` of each runner and its `pi-tui` companion | Never blocks. Runs on schedules and on demand from a web pipeline. |

The canary rewrites the runner specs to `@latest` with `bun add --dev` inside the
job's disposable checkout, so no manifest or lockfile is ever committed from it. It
needs a pipeline schedule on the project to run daily.

It only runs checks that can run on another runner version. Pi runs its full
extension contract. The OMP harness is a golden-file contract locked to its pinned
runner (committed fixtures and `contract-snapshot.json`, which also records the
package versions), so on any other version everything behind that lock fails by
design. Its canary is therefore the typecheck against the latest runner types plus
`discovery-contract.test.ts`.

A red canary means upstream changed. Bump the pins in a normal merge request (for
OMP also run `bun run lock` to regenerate `contract-snapshot.json`); the required
lane then verifies the bump.

## OpenCode's declared target

OpenCode is different because Slopgate declares the version it supports in code:
`_OPENCODE_API_TARGET` in `src/slopgate/installer/opencode_identity.py`, repeated
in `package.json`, `bun.lock`, the plugin header, and
`tests/integration/test_opencode_real_host.py`. That contract suite skips itself on
any other OpenCode version, so a newer host would otherwise go unnoticed.

```bash
make harness-drift   # reports releases ahead of the declared target; exit 0 on drift
```

The release source is `@opencode/plugin` (the 2.x host ships in lockstep with its
SDK; `opencode-ai` is the 1.x line). Adopting a release is a deliberate change to
those targets, verified by the real-host contract suite. The script exits non-zero
only when the registry or the declared target cannot be read.

To track another harness whose version is declared in code, add a `DeclaredTarget`
(name, npm package, reader for the declared version) to `DECLARED_TARGETS` in
`scripts/harness_target_drift.py`.
