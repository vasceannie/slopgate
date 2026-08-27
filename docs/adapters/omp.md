# OMP adapter

OMP is registered in Slopgate's installer, suite discovery, CLI platform registry,
and dashboard trace surfaces. Dashboard harness-status probing remains deferred
until OMP exposes a stable status contract.

## Dashboard deferrals

| Selector | Status | Reason |
|---|---|---|
| `HarnessPlatformStatus.id` | Deferred | The dashboard status response does not yet model OMP. |
| `dashboard/scripts/forcedash_server/remote_scripts/harness_status.py.txt` | Deferred | Remote OMP harness discovery is not part of Todo 5. |
