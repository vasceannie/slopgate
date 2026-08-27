# OMP adapter

OMP is registered in Slopgate's installer, suite discovery, CLI platform registry,
and dashboard trace surfaces. Dashboard harness-status probing remains deferred
until OMP exposes a stable status contract.

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
