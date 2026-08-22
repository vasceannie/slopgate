# OpenCode mutation-hook latency

OpenCode awaits typed `tool.execute.before` and `tool.execute.after` plugin hooks. Slopgate therefore treats the latency of its generated plugin and hook subprocess as interactive latency. OpenCode does not document a hook timeout, ordering guarantee, concurrency guarantee, or latency SLO; the target below belongs only to Slopgate.

## Slopgate target

For an enrolled repository comparable to the Slopgate repository, the awaited post-mutation path should meet both of these thresholds:

- p50 total latency at or below **1,000 ms**
- p95 total latency at or below **1,250 ms**

The benchmark must also report identical decisions and stable finding signatures across measured iterations. A latency result is not comparable unless its repository, touched-content, policy, and Slopgate OpenCode projection-contract fingerprints are recorded.

This target is deliberately above the current baseline to tolerate normal workstation and filesystem variation without misrepresenting it as an OpenCode contract.

## Reproduce

From an enrolled Slopgate checkout with Bun and the project virtual environment installed:

```bash
uv run scripts/benchmark_opencode_mutation.py --iterations 10 --warmup 2
```

The benchmark renders the installed OpenCode plugin, drives its real awaited `tool.execute.after` handler, forces the direct-engine fallback through an isolated nonexistent daemon socket, and records:

- total hook latency
- plugin dispatch overhead
- subprocess startup
- normalization/context construction
- rule-engine execution
- touched-file lint collector execution
- response rendering
- trace-event writing
- repository size and touched-content fingerprint
- OpenCode, plugin, Slopgate, policy, and projection-contract identities
- decision and stable-finding parity

## 2026-08-22 baseline

The representative sample contained 1,565 tracked files and 16,056,777 tracked bytes. The touched target was `src/slopgate/lint/_helpers/parsing.py` at 9,228 bytes. OpenCode was `1.18.21`; the Slopgate-owned projection contract was `slopgate-opencode-projection-v1`; Slopgate was `2.1.6`. The projection contract is independent of OpenCode's release number and changes only when Slopgate changes the projected payload schema.

Ten measured iterations after two warmups produced:

| Phase | p50 | p95 |
|---|---:|---:|
| Total awaited hook | 790.903 ms | 812.270 ms |
| Dispatch | 25.418 ms | 30.702 ms |
| Subprocess startup | 122 ms | 129 ms |
| Evaluation | 640 ms | 657 ms |
| Rule engine | 638 ms | 654 ms |
| Touched-file collectors | 590 ms | 610 ms |
| Normalization/context | 0 ms | 1 ms |
| Rendering | 0 ms | 0 ms |
| Trace event | 0 ms | 0 ms |

Decisions and stable finding signatures were identical across all iterations. The touched-file collectors are the dominant cost and remain awaited so policy behavior is preserved.

Before optimization, local post-mutation trace rows recorded 7,142 ms and 7,415 ms. Those two observations are not a percentile baseline, but they establish the original user-visible range; the reproducible post-optimization p95 is about 89% lower than the lower observation while retaining decision and finding parity.

The benchmark also reports installed OpenCode plugin version skew. Version-skew warnings must be resolved before using a run as release evidence because installed plugin behavior is version-scoped.
