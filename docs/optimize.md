# Slopgate Hook Performance Optimization Plan

## Summary

The optimization should reduce hook latency without weakening enforcement by separating immediate deterministic checks from expensive repo/suite analysis, then sharing one rule/collector catalog across hooks and CLI lint. Enforcement must be best-effort across every supported platform; do not assume Claude is primary or that every platform can hard-block the same phase.

Current measured hotspots:

- `PreToolUse` synthetic `Write`: about `550ms` warm in-process, dominated by enrichment citation scanning.
- `PostToolUse` synthetic `Write`: about `4.49s` warm in-process, dominated by `PostEditLintRule` running broad touched collectors, test-integrity indexing, constant-index discovery, and reference-test parsing.
- The installed POSIX Node daemon proxy uses a `1s` timeout while the Python daemon client uses `30s`, so slow daemon requests can fall back to direct CLI and duplicate work.
- A watcher can help, but only as a bounded invalidation layer for a deterministic project index. It must never become the enforcement authority.

## Scope Locks

- **Platform target:** preserve the strongest available enforcement on every supported platform. Where a platform cannot hard-block `PostToolUse` or `Stop`, emit stable advisory findings, trace records, and dashboard-visible evidence instead of pretending parity.
- **Public compatibility:** do not change public hook rule IDs, lint collector IDs, counterpart mapping semantics, baseline stable IDs, trace payload shapes, dashboard grouping keys, renderer semantics, or CLI output semantics. Add catalog metadata around the existing public contracts.
- **Immediate blockers:** duplicate/code-clone checks, repeated literal checks, and project constant-scan-backed literal guidance must remain in the immediate post-edit path. They may be optimized through bounded indexes/caches and narrower discovery, but they must not be deferred entirely to Stop/CLI. Any bounded immediate finding must cite explicit preexisting references, such as file paths, line numbers, constant names, matching duplicate fingerprints, or nearby source/test evidence; vague hook responses are forbidden.
- **First-pass scope:** watcher-backed invalidation is not part of the first performance pass. The first pass should fix proxy semantics, add catalog-driven routing, split safe-to-defer collectors, add request-local AST/source caching, bound enrichment, and add benchmarks.
- **Daemon acceptance boundary:** a daemon request is accepted only after daemon acknowledgement through an `accepted` field in the existing response envelope. If acknowledgement is missing, the proxy may fall back before sending/acknowledgement; after acknowledgement, timeout/error handling must fail closed and must not run the same hook through direct CLI.
- **Trace metrics:** no-finding timing must be configurable, dashboard-safe, and recorded in `results.jsonl` metadata by default. Prefer aggregated per-evaluation and collector-group timing by default; per-rule no-finding traces must be opt-in so JSONL volume does not break replay or dashboard usability.
- **Cache posture:** use cautious conservative defaults with explicit hard caps, LRU eviction, and short idle eviction. Initial targets should be benchmark-adjusted, but start near `64 MiB` per repo for compact project metadata, `16 MiB` per hook evaluation for request-local AST/source analysis, `256 KiB` maximum cached source text per file, and `10 minutes` idle eviction for daemon repo sessions.

## Performance Targets

Use aggressive but adjustable targets measured as `p50` and `p95` across direct CLI, daemon, and installed POSIX proxy paths. Benchmarks must record cold and warm runs, daemon unavailable runs, cache-disabled runs, and representative small/medium repositories.

Initial targets:

- Warm `PreToolUse` single-file write: `p95 <= 250ms`.
- Warm `PostToolUse` single-file Python edit with immediate duplicate/literal/constant checks enabled: `p95 <= 900ms`.
- Cold `PostToolUse` single-file Python edit through installed proxy: `p95 <= 2.5s`.
- Direct CLI fallback for the same hook, no daemon and no warm cache: `p95 <= 3s`.
- Stop/deferred quality pass over uncommitted changes: `p95 <= 5s` for a medium repo, with clear trace output when it degrades or defers.
- Installed POSIX proxy daemon-ack path: no duplicate direct-CLI execution after acknowledgement, regardless of timeout.

## Key Changes

1. **Create a shared collector/rule catalog.**
   - Add metadata for each lint collector and hook rule: stable ID, counterpart IDs, `scope` (`file`, `touched`, `project`, `suite`, `git-base`), `cost`, supported events, supported surfaces, default action, and deferred eligibility.
   - Keep the existing finding/violation payloads, renderers, baseline IDs, and CLI output semantics unchanged.
   - Absorb the existing parity contract into the catalog rather than creating a second source of truth beside `slopgate.lint._parity`.
   - Use the catalog from hooks, CLI lint, Stop checks, dashboard/reporting, and async quality paths instead of maintaining separate rule lists.

2. **Split immediate hook checks from deferred repo/suite checks.**
   - `PreToolUse`: run only deterministic checks based on tool input, touched content, and cheap metadata.
   - `PostToolUse`: run touched-file and touched-test checks that can be bounded to changed paths or nearby context, plus immediate duplicate/code-clone checks, repeated literal checks, and project constant-scan-backed literal guidance.
   - `Stop`: run safe-to-defer project/suite checks over uncommitted changes using the same collector catalog. Stop must supplement immediate enforcement, not replace it where a platform cannot reliably block.
   - `CLI lint`: remain the authoritative full scan and must still be able to run without daemon, watcher, or warm cache.
   - Checks eligible to move out of the hot post-tool path include full test-integrity indexing, missing integration detection, obsolete test refs, mock-theater, schema bypass, and hand-built payload detection when they cannot be bounded to the touched edit.
   - Checks not eligible for full deferral in this pass: duplicate/code-clone checks, repeated literals, and project constant scans needed to make repeated-literal guidance enforceable. The implementation may replace broad scans with cached/bounded scans, but it must still make the immediate blocking decision in `PostToolUse` and must render explicit references to the preexisting duplicate, repeated literal, or constant evidence.

3. **Add a repo-scoped deterministic `ProjectIndex`; defer watcher-backed invalidation.**
   - Define a deterministic `ProjectIndex` interface for file inventory, source/test classification, constant candidates, parsed summaries, test references, imports, logger conventions, duplicate fingerprints, and dirty path sets.
   - Start with a local implementation backed by current parsing and discovery helpers.
   - Keep the first implementation deterministic and callable from direct CLI paths; do not require daemon state or watcher support for correctness.
   - Leave optional daemon-owned file/tree watcher support as a later acceleration layer that records changed paths and invalidates compact indexes.
   - Store compact metadata by default: paths, mtimes, sizes, hashes where needed, file kind, symbol summaries, and fingerprints. Do not store the full tree contents.
   - Keep parsed ASTs and source text in bounded LRU caches only.
   - For later watcher support, watcher overflow, rename storms, config changes, git checkout, missing watcher support, or stale signatures must mark the index stale and fall back to deterministic scan or defer to Stop/CLI.
   - Expose optional future adapters for CodeGraph, GitNexus, or ISX, but do not require them for enforcement.

4. **Fix daemon proxy semantics.**
   - Align installed POSIX Node proxy timeout and accepted-request behavior with the Python daemon client.
   - If the daemon cannot be contacted before sending a request, direct CLI fallback is allowed.
   - Add an explicit `accepted` field to the existing daemon response envelope after the daemon receives and admits the request.
   - If `accepted` is true, timeout/error handling must not duplicate the same hook by falling back to direct CLI.
   - If `accepted` is absent or false, fallback is allowed only when the proxy can prove the hook was not admitted for evaluation.
   - Preserve fail-closed behavior and explicit stderr/exit-code reporting.

5. **Share per-request Python analysis across hook rules.**
   - Add a request-local analysis cache keyed by path plus source signature.
   - Cache parsed module, functions, classes, imports, line/token summaries, parent maps, and reusable AST walks.
   - Update Python AST helpers so local hook rules reuse the same analysis instead of reparsing the touched file per rule.
   - Clear request-local analysis at the hook evaluation boundary and daemon request boundary.

6. **Make enrichment bounded and phase-aware.**
   - Fix repo-relative path resolution so enrichment uses the actual repo root before falling back to broader discovery.
   - Run cheap enrichment inline.
   - Use the `ProjectIndex` for expensive citations when fresh; otherwise bound lookup to nearby files or defer rich context to Stop/reporting.
   - Blocking decisions must not wait on expensive explanatory citation discovery once the violation is already known.

7. **Reduce trace/log overhead while preserving replayability.**
   - Buffer trace writes per hook evaluation and flush once, including failure paths.
   - Keep JSONL trace structure stable for replay.
   - Gate verbose internal trace-write logs behind a configured log level.
   - Add configurable, dashboard-safe timing for no-finding rules and collector groups in `results.jsonl` metadata so future performance regressions are visible without bloating JSONL by default.

## Hook And CLI Interoperability Requirements

- `PreToolUse`, `PostToolUse`, `Stop`, and CLI lint must all consume the same rule/collector catalog for any rule family touched by this work.
- Surface differences must be data-driven through rule metadata and `RuleSurfaceConfig`, not forked implementations.
- A rule or collector touched by this work must preserve its existing stable public ID and add exactly one catalog counterpart mapping when it has related hook/CLI surfaces.
- Hook-specific execution may differ by phase and scope, but semantic meaning of each finding must remain identical to CLI lint.
- Deferred checks must produce the same collector IDs and stable IDs they would produce in CLI lint.
- The watcher/index must sit below hooks and CLI as an acceleration provider; correctness must still hold when it is disabled.
- Best-effort platform behavior must be explicit in metadata and traces. If a surface is advisory-only on a platform, the finding must still keep stable IDs, payload fields, and remediation context.

## Completion Criteria

The work is complete only when all of the following are true:

- **Catalog wired:** every touched hook rule and lint collector is registered in the shared catalog with scope, cost, surfaces, events, action, deferred eligibility, public ID preservation, and counterpart IDs.
- **Hooks wired:** `PreToolUse`, `PostToolUse`, and `Stop` route touched rule families through the shared catalog and project-index interface where applicable, without assuming any single platform is primary.
- **CLI wired:** CLI lint uses the same catalog and can force a fresh full scan that does not depend on daemon state, watcher state, or warm caches.
- **Deferred path wired:** expensive project/suite collectors removed from the immediate post-tool hot path are reachable from Stop and CLI lint with the same IDs and result schema, while duplicate/code-clone, repeated-literal, and project-constant-scan-backed checks remain immediate blockers.
- **ProjectIndex wired:** deterministic local `ProjectIndex` use is covered for hooks and CLI without requiring daemon state, watcher state, or external code-intelligence services.
- **Watcher deferred:** watcher-backed invalidation is explicitly outside the first performance pass unless all earlier completion criteria are already met.
- **Cache limits wired:** AST/source/index caches have explicit memory budgets, per-repo idle eviction, and overflow behavior covered by tests.
- **Proxy wired:** installed POSIX daemon proxy behavior matches Python client semantics for timeout, the `accepted` response-envelope field, accepted request failure, direct fallback, stderr, and exit codes.
- **Trace wired:** every hook evaluation still writes replayable JSONL trace output, including index freshness/fallback decisions, deferred collector routing, and dashboard-safe timing summaries in `results.jsonl` metadata.
- **Interoperability proved:** tests demonstrate that touched rule families report the same semantic violation IDs and payloads from hook, Stop, and CLI surfaces where each surface supports that rule.
- **Performance proved:** warm single-file `PostToolUse` no longer invokes full test-integrity indexing by default, preserves immediate duplicate/literal/constant enforcement, and meets or beats the documented p95 targets against the current multi-second baseline.
- **Quality proved:** the implementation passes focused unit/integration tests plus the project quality command, with any remaining baseline debt explicitly unrelated to the touched files.

## Test Plan

- Add collector-catalog tests proving each touched collector/rule has complete metadata and counterpart mapping.
- Add hook-selection tests for `PreToolUse`, `PostToolUse`, and `Stop` showing phase-appropriate collector routing.
- Add CLI parity tests proving full lint still runs all collectors and reports existing collector IDs and payload shapes consistently with deferred hook checks.
- Add deterministic `ProjectIndex` tests for path changes, deletes, renames, stale config, disabled cache/index use, idle eviction, memory cap eviction, and fallback scans.
- Add later-phase watcher tests for overflow, stale config, missing watcher support, rename storms, and deterministic fallback before enabling watcher-backed invalidation.
- Add daemon concurrency tests proving repo-scoped indexes remain isolated and same-repo serialization still protects mutable state.
- Add proxy tests for connection failure fallback, the daemon `accepted` response-envelope field, unacknowledged request fallback, acknowledged slow request handling, timeout behavior, stderr preservation, and fail-closed outcomes.
- Add AST-cache tests proving multiple local Python rules parse a touched source once per hook evaluation.
- Add enrichment tests for repo-relative path resolution, bounded lookup, cached citation reuse, and stale-index fallback.
- Add trace tests proving buffered traces flush on success, block, error, and daemon fallback paths without changing replay semantics or dashboard assumptions.
- Add configuration tests for no-finding timing modes, including default aggregated timing in `results.jsonl` metadata and opt-in per-rule no-finding trace emission.
- Add performance regression tests or benchmark fixtures for representative single-file `PreToolUse`, `PostToolUse`, direct CLI fallback, installed POSIX proxy, daemon, and Stop runs.

## Recommended Sequence

1. Add benchmark fixtures and contract tests for current IDs, payloads, trace shape, direct CLI, daemon, and installed proxy behavior.
2. Fix daemon proxy timeout/fallback semantics with the daemon `accepted` response-envelope field and add regression tests.
3. Add the shared collector/rule catalog by absorbing the existing parity/counterpart contract without changing execution.
4. Route `PostToolUse` collector selection through the catalog while preserving immediate duplicate/code-clone, repeated-literal, and project-constant-scan-backed blockers.
5. Move only safe-to-defer project/suite collectors to Stop/CLI while preserving IDs and payloads.
6. Add the `ProjectIndex` interface with local deterministic implementation and conservative cache budgets.
7. Add request-local AST/source analysis caching for Python hook rules.
8. Bound enrichment and route expensive citation lookups through deterministic index/cache data where fresh.
9. Buffer trace writes and add configurable no-finding timing metrics in `results.jsonl` metadata that are safe for dashboard/replay consumers.
10. Run full interoperability, performance, and quality verification.
11. Add bounded watcher-backed invalidation inside daemon repo sessions only after the deterministic first pass meets the criteria above.

## Assumptions

- Immediate hooks must continue blocking deterministic local violations.
- Best-effort enforcement applies to every supported platform; do not design around Claude as the primary or only hard-blocking reference.
- Expensive project/suite checks may move phases only when the catalog marks them safe to defer and immediate enforcement is not weakened on platforms with advisory Stop/PostToolUse behavior.
- Duplicate/code-clone checks, repeated literals, and project constant scans needed for repeated-literal guidance remain immediate blockers in this pass.
- CLI lint remains the authoritative complete quality gate.
- Watcher and external indexes are optimizations only; stale or unavailable indexes cannot change correctness.
- Platform limitations still apply: where Stop cannot reliably block, it must emit explicit advisory findings with stable IDs and trace records.
- Public IDs, baseline stable IDs, trace payload shapes, renderer semantics, CLI output semantics, and dashboard grouping keys are compatibility contracts and must not change.
