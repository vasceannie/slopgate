## 1. Decision-complete conclusion

Slopgate can build a deterministic improvement-measurement layer from `results.jsonl` without transcript mining or an LLM. The runtime already records session identity, repo and enforcement mode, platform capability, model/provider, tool input and mutation intent, findings, rule errors, and timings. `slopgate stats` already owns the canonical loader and report path. `src/slopgate/engine/_evaluation.py:139-153`, `src/slopgate/engine/_evaluation.py:175-196`, `src/slopgate/stats/_load.py:50-71`, `src/slopgate/stats/_report.py:160-182`

The implementation target is **Slices 1 through 4**:

1. complete and fingerprint result traces,
2. add canonical single-window improvement metrics,
3. add guarded baseline-vs-candidate comparisons, and
4. make the dashboard mirror the same tested semantics.

Transcript enrichment remains out of scope.

The original delivery order was unsafe. Outcome metrics must not become authoritative before version, policy, guidance, path, and language provenance exists. A policy change can otherwise look exactly like an agent repair. Trace completeness and the canonical episode contract therefore land before authoritative reporting.

## 2. Confirmed problems

| Severity | Finding | Evidence | Required correction |
| --- | --- | --- | --- |
| **P1** | `first_time_resolution_rate` calls a scope resolved when it was denied only once; no clean follow-up is observed. | `src/slopgate/stats/_analysis.py:164-177`, `src/slopgate/stats/_analysis.py:190-192`, `src/slopgate/stats/_report.py:141-157` | Preserve the field as legacy churn telemetry. Add outcome-valid metrics with explicit denominators and censoring. |
| **P1** | Dashboard session resolution treats any later non-blocking result as resolution. | `dashboard/src/hooks/useTraceData.ts:1091-1136` | Replace the operational metric with rule-local repair episodes. |
| **P1** | Result rows omit `candidate_paths` and `languages`, although start rows contain them. | `src/slopgate/engine/_evaluation.py:156-196`, `dashboard/src/context/traceRecordValidation.ts:34-47` | Add both fields to result rows and dashboard result types. |
| **P1** | Result rows have no policy, guidance, or implementation provenance. | `src/slopgate/engine/_evaluation.py:175-196` | Add Slopgate version plus deterministic policy and guidance fingerprints. |
| **P2** | Dashboard calibration hashes the complete mutable `tool_input`. | `dashboard/src/lib/ruleCalibration.ts:42-61` | Use content-independent semantic scope identity. |
| **P2** | Python stats, dashboard session operations, and dashboard calibration define improvement differently. | `src/slopgate/stats/_analysis.py:131-192`, `dashboard/src/lib/ruleCalibration.ts:90-332`, `dashboard/src/hooks/useTraceData.ts:1091-1136` | Define one pure contract in Python and mirror it in TypeScript against shared fixtures. |
| **P2** | Aggregate metrics can mix `repo_strict`, `repo_relaxed`, and `outside_repo`. | `src/slopgate/engine/_runner.py:229-267`, `tests/engine/test_12_enforcement_modes.py:33-111` | Use strict-mode metrics as the headline and always show the other modes as separate cohorts. |

One boundary remains explicitly outside this plan: the implementation and schema behind `make eval-dataset-ats` were not established. This strategy targets runtime `results.jsonl` data.

## 3. Locked product decisions

These decisions are implementation requirements, not open questions.

| Area | Decision |
| --- | --- |
| Delivery scope | Implement Slices 1 through 4. Do not implement transcript enrichment. |
| Canonical model | Use two related models: a scope-level first-observed outcome and block-anchored rule-local repair episodes. |
| Legacy rows | Show unversioned rows as best-effort `unknown_policy` diagnostics. Never mix them with fingerprinted authoritative comparisons. |
| Multi-path identity | Prefer paths implicated by finding metadata. Otherwise retain the normalized candidate-path set as one low-confidence compound scope. |
| Fingerprints | Keep `slopgate_version`, enforcement behavior, and runtime guidance as separate provenance fields. |
| Rule-source changes | Effective policy identity must change when enforcement source changes even if the package version was not bumped. |
| Resolution | Rule X resolves when a comparable result omits enforcing X and contains no evaluation error for X. Other rules may still fire. |
| Tool comparability | Compare semantic tool families, so Write, Edit, MultiEdit, and apply-patch-style file mutations can repair one another on the same target. |
| Observation end | Scan all available same-session rows until resolution, provenance change, or end of available data. |
| Stats output | Every stats report includes a nested, versioned `improvement` object. Existing top-level keys and formulas remain unchanged. |
| Dashboard | Python defines the canonical contract. TypeScript mirrors the pure evaluator so uploaded raw JSONL remains analyzable in-browser. |
| Enforcement modes | Headline coding metrics use `repo_strict`. Relaxed and outside-repo metrics are always reported separately. |
| Comparisons | Always show stratified breakdowns. Suppress the headline aggregate when matched filters do not isolate the selected intervention. |

## 4. Canonical measurement model

### 4.1 Result record prerequisites

Every new result row must contain:

```text
candidate_paths
languages
slopgate_version
effective_policy_fingerprint
guidance_fingerprint
```

Existing fields remain unchanged. New dashboard fields are optional during ingestion so historical rows continue to load.

Legacy rows without fingerprints are classified as `unknown_policy`. They may appear in diagnostic counts and best-effort single-window summaries, but they cannot enter an authoritative baseline/candidate comparison.

### 4.2 Semantic tool families

Attempt identity uses semantic families rather than exact tool names:

```text
file_mutation  = Write, Edit, MultiEdit, apply_patch, equivalent adapter-normalized writes
shell          = Bash and equivalent shell execution
search         = Glob, Grep, indexed/semantic search tools
web            = WebFetch, WebSearch, equivalent web tools
lifecycle      = Stop, SessionEnd, task/session lifecycle events
other          = any remaining canonical tool/event pair
```

Families must remain narrow enough that an unrelated shell or read operation cannot resolve a blocked file mutation.

### 4.3 Path identity and confidence

For a blocking finding, select target paths in this order:

1. normalized paths explicitly implicated by finding metadata,
2. normalized result-level `candidate_paths`, retained as one compound set,
3. a pathless sentinel.

Normalize paths by converting separators to POSIX form, resolving `.` and `..`, making in-repo paths relative to `resolved_repo_root`, preserving normalized absolute paths outside the repo, removing duplicates, and sorting compound sets.

Confidence is explicit:

```text
high   = one or more finding-implicated paths
medium = candidate-path compound scope
low    = pathless scope
```

Do not explode a multi-path attempt into one episode per path. That would double-count attempts and attribute findings to files the rule may not have implicated.

### 4.4 Scope-level first-observed outcome

`first_attempt_clean_rate` is not rule-specific because a clean attempt has no rule identity.

Define a structural scope identity first:

```text
session_id
+ resolved_repo_root
+ semantic tool family
+ normalized target path set
```

The cohort scope key adds enforcement and provenance:

```text
structural scope identity
+ enforcement_mode
+ slopgate_version
+ effective_policy_fingerprint
+ guidance_fingerprint
```

For each mutating scope, inspect only its first observed result:

```text
clean   = no deny/block finding
blocked = one or more deny/block findings
```

Advisory findings do not make the attempt blocked.

### 4.5 Rule-local repair episodes

A repair episode begins only when a rule produces `deny` or `block`.

The episode key adds `rule_id` to the scope-level key. Source content, full `tool_input`, command text, and rendered output are excluded.

After the initial block, later rows are comparable only when they have:

- the same session,
- the same repo root,
- the same enforcement mode,
- the same semantic tool family,
- the same normalized target-path identity,
- the same Slopgate version,
- the same policy fingerprint, and
- the same guidance fingerprint.

The target rule's initial block proves that it was active for that provenance. A comparable later result resolves rule X when:

1. no enforcing finding for X is present, and
2. `errors` contains no `X: ...` rule-evaluation error.

Errors from another rule do not censor X. Enrichment errors do not censor X. Partial or degraded platform capability does not automatically censor the result; platform and capability remain cohort dimensions, and comparable attempts require stable provenance.

Episode states are:

```text
resolved
still_failing
no_observed_followup
provenance_changed
evaluation_error
```

`never_blocked` is not a repair-episode state. It belongs to the scope-level first-observed model.

State rules:

- `resolved`: first comparable result where X is absent and X did not error.
- `still_failing`: at least one comparable follow-up exists and the latest comparable result still enforces X.
- `no_observed_followup`: no comparable follow-up exists before available session data ends.
- `provenance_changed`: later activity matches the structural scope identity, but version/policy/guidance/enforcement provenance changed before a comparable resolution was observed.
- `evaluation_error`: structurally comparable activity exists, but the last available evidence for X is an `X: ...` evaluation error and no later valid comparable result resolves or persists X.

After resolution, a later block for the same key starts a new episode.

## 5. Metrics and denominators

The nested `improvement` object must expose raw counts and derived rates.

### 5.1 Required single-window metrics

1. **Blocking evaluations per 100 mutating evaluations**
   - numerator: mutating results ending in deny/block
   - denominator: all mutating results

2. **First-attempt clean rate**
   - numerator: first-observed mutating scopes classified `clean`
   - denominator: all first-observed mutating scopes

3. **Observed repair success rate**
   - numerator: resolved episodes
   - denominator: resolved plus still-failing episodes
   - excluded but reported: `no_observed_followup`, `provenance_changed`, `evaluation_error`

4. **Repair attempts**
   - one repair attempt is one comparable follow-up after the initial block
   - report median and p90 for resolved episodes

5. **Repair latency**
   - elapsed wall time from initial block to first resolving result
   - report median and p90 for resolved episodes

6. **Persistence rate by rule**
   - numerator: comparable follow-ups where the same rule still enforces
   - denominator: all comparable follow-ups for that rule

7. **Runtime reliability**
   - result error rate
   - p50 and p95 `evaluation_ms`
   - p50 and p95 `rule_engine_ms`

8. **Cohort distribution**
   - repo
   - enforcement mode
   - platform and capability
   - model/provider
   - rule
   - event/tool family
   - language
   - Slopgate version
   - policy fingerprint
   - guidance fingerprint
   - scope confidence

Do not create a scalar Slopgate improvement score.

### 5.2 Enforcement-mode presentation

The report always contains separate mode cohorts:

```text
repo_strict
repo_relaxed
outside_repo
```

Only `repo_strict` contributes to the headline coding-improvement metrics. Relaxed and outside-repo cohorts remain visible so disabling or bypassing strict policy cannot masquerade as improvement. Runtime health is reported for every mode.

## 6. Provenance fingerprints

### 6.1 Slopgate version

Record `slopgate.__version__` directly as `slopgate_version`. `src/slopgate/_version.py:1`

### 6.2 Effective policy fingerprint

`effective_policy_fingerprint` represents enforcement behavior, not raw config text and not user-facing guidance wording.

Hash a canonical, secret-free projection containing:

- built-in and declarative enforcement rule source digests,
- resolved rule enablement and disabled rules,
- resolved hook events and surface actions,
- severity overrides,
- regex rule definitions that affect matching or decisions,
- enforcement thresholds,
- skip/disable semantics,
- protected/sensitive/system path policy,
- post-edit blocking behavior, and
- other resolved fields that can change whether a finding is emitted or enforced.

Exclude:

- trace paths,
- timestamps,
- repo absolute path as data rather than policy,
- model/provider,
- platform/capability,
- raw source content,
- command text, and
- user-facing guidance text.

Use SHA-256 over deterministically serialized JSON. Source digests ensure local rule changes alter policy identity even when `slopgate_version` is unchanged. The existing lint `engine_fingerprint()` is precedent, but this fingerprint must use content digests rather than file mtimes. `src/slopgate/lint/project_index/fingerprint.py:38-101`

Some rule modules contain enforcement logic and user-facing text in the same source file. When a guidance-only change cannot be separated safely from enforcement source, conservatively allow both fingerprints to change. False cohort separation is preferable to merging semantically different runs.

### 6.3 Guidance fingerprint

`guidance_fingerprint` represents runtime guidance Slopgate can emit for the evaluation.

Hash a canonical projection of:

- rule messages and additional-context templates,
- `RULE_HINTS`, `QUALITY_COLLECTOR_HINTS`, and `REPLAN_PROMPT`,
- quality-lint repair guidance templates,
- configured hook guidance values, and
- configured prompt-context file contents when those files are part of runtime hook context.

Do not include unrelated installed bundle assets merely because they exist on disk. In particular, do not hash the entire shared skill library or prompt bundle unless the runtime evaluation actually incorporates that asset. Transcript-level attribution of broader agent instructions remains Slice 5 work.

## 7. Stats and JSON contract

Existing top-level `analyze()` output remains backward compatible. In particular:

- preserve `first_time_resolution_rate` with its current formula,
- add `single_deny_scope_rate` as an honest alias,
- label both as legacy in the human report, and
- do not reinterpret existing keys silently.

Every stats run adds:

```json
{
  "improvement": {
    "schema_version": 1,
    "authoritative": true,
    "legacy_rows": {
      "count": 0,
      "included_in_comparisons": false
    },
    "headline": {},
    "by_enforcement_mode": {},
    "by_rule": {},
    "cohorts": {},
    "episodes": {},
    "runtime": {},
    "comparison": null
  }
}
```

If only legacy rows are available, `authoritative` is false and the object explains why.

The human report always includes a concise improvement section. No `--improvement` opt-in flag is required.

Comparison selectors extend the existing command:

```text
slopgate stats --baseline-policy <hash-a> --candidate-policy <hash-b>
slopgate stats --baseline-guidance <hash-a> --candidate-guidance <hash-b>
slopgate stats --baseline-policy <hash-a> --candidate-policy <hash-b> --json
slopgate stats --baseline-policy <hash-a> --candidate-policy <hash-b> \
  --cohort enforcement_mode=repo_strict --cohort platform=claude
```

Each baseline/candidate selector pair is all-or-nothing. At least one complete policy or guidance pair is required for a comparison. Missing or unknown fingerprints are CLI input errors, not empty successful comparisons. `--cohort dimension=value` is repeatable for repo, enforcement mode, platform, capability, model, provider, rule, language, version, policy, guidance, and scope confidence.

## 8. Baseline-vs-candidate comparison contract

An `ImprovementComparison` contains:

```text
baseline provenance and counts
candidate provenance and counts
matched cohort dimensions
absolute deltas
relative deltas
sample counts
confounding dimensions
aggregate availability and suppression reason
```

Always emit breakdowns for repo, enforcement mode, platform/capability, model/provider, rule, language, and scope confidence.

The headline aggregate is available only when the selected rows have identical repo, enforcement-mode, platform/capability, model/provider, and language facet values after cohort filters, except for the fingerprint dimension intentionally selected as the intervention. Otherwise the report remains stratified.

If the selected cohorts also differ in version, non-selected fingerprints, model, provider, or platform mix:

- emit the stratified breakdowns,
- set the aggregate to unavailable,
- report the confounding dimensions, and
- do not describe the result as causal improvement.

No automatic statistical reweighting is included in this scope.

## 9. Dashboard convergence

Python is the semantic authority. The browser must still support raw uploaded JSONL, so the dashboard implements a pure TypeScript mirror rather than depending exclusively on the ForceDash server.

Requirements:

1. Create shared language-neutral fixtures containing representative result sequences and expected scope/episode/metric outputs.
2. Require Python and TypeScript evaluators to produce the same contract for every fixture.
3. Extend `HookResult` and trace normalization with optional paths, languages, version, and fingerprint fields.
4. Replace the broad session `resolutionRate` calculation with episode-based observed repair success.
5. Replace content-bearing calibration identity with the canonical semantic scope identity.
6. Preserve calibration triage fields unless their meaning is explicitly migrated; outcome truth comes from the episode evaluator.
7. Show legacy/unknown-policy and confounded-comparison status in the UI rather than silently merging those rows.

`dashboard/src/hooks/useTraceData.ts:1091-1136`, `dashboard/src/lib/ruleCalibration.ts:54-61`, `dashboard/src/context/traceRecordValidation.ts:304-380`

## 10. Required behavioral tests

The shared fixture suite must include at least:

```text
blocked Write(path A, content v1)
-> clean Edit(path A, content v2)
= rule resolved in 1 repair attempt

blocked Write(path A)
-> allowed Bash(git status)
= no comparable follow-up

blocked Write(path A)
-> clean Write(path B)
= no comparable follow-up

blocked rule X(path A)
-> comparable result with rule Y(path A)
= X resolved if X did not error

blocked rule X(path A)
-> comparable result with error "X: detector crashed"
= X not resolved; episode ends as evaluation_error if no later valid comparable result exists

blocked rule X(path A)
-> comparable result with error for rule Y
= X may resolve if X is absent

blocked multi-path attempt with finding metadata path A
-> clean attempt on A
= high-confidence resolution

blocked multi-path attempt without finding path metadata
-> clean attempt with same candidate-path set
= medium-confidence resolution

single block with no comparable follow-up
= no_observed_followup

block followed by policy, guidance, version, or enforcement-mode change
= provenance_changed, not resolved

clean first mutating scope
= first-attempt clean without inventing a rule identity

legacy row without fingerprints
= diagnostic only; excluded from authoritative comparison
```

Additional gates:

- fingerprint determinism across dictionary/set ordering,
- fingerprint changes for rule-source, enablement, action, severity, threshold, regex, and runtime-guidance changes,
- no fingerprint changes for timestamps, trace paths, or unrelated bundle assets,
- Python/TypeScript fixture parity,
- existing stats JSON keys and formulas preserved,
- dashboard upload mode computes the same results as live mode, and
- aggregate comparison suppressed when confounders remain.

## 11. Delivery order

### Milestone 1: Trace completeness and contract fixtures

- Add result-level paths, languages, version, policy fingerprint, and guidance fingerprint.
- Define canonical record, scope, episode, metric, and comparison schemas.
- Add shared fixtures before exposing authoritative rates.

### Milestone 2: Python evaluator and stats integration

- Add the pure scope and episode evaluator under `src/slopgate/stats/`.
- Add single-window metrics and runtime reliability.
- Preserve legacy top-level fields.
- Emit the nested versioned `improvement` object on every stats run.
- Report strict, relaxed, and outside-repo cohorts separately.

### Milestone 3: Guarded cohort comparison

- Add baseline/candidate policy and guidance selectors plus repeatable cohort filters.
- Emit raw counts, absolute and relative deltas, facet distributions, confounders, and aggregate suppression reasons.
- Never mix fingerprinted and `unknown_policy` rows in authoritative comparisons.

### Milestone 4: Dashboard convergence

- Mirror the pure evaluator in TypeScript.
- Enforce shared-fixture parity.
- Replace broad session resolution and mutable-content calibration scope.
- Preserve raw upload support and display provenance confidence.

### Deferred: transcript enrichment

Do not add transcript mining, cross-harness conversation reconstruction, or LLM-based causal explanation in this implementation.

## 12. Completion criteria

The implementation is complete only when:

- new result rows are self-sufficient for path, language, and provenance analysis,
- first-attempt clean and repair success use the separate locked models,
- rule-local resolution is error-aware and provenance-stable,
- every rate includes raw numerator, denominator, and censored counts,
- strict and non-strict cohorts cannot be silently mixed,
- legacy rows cannot enter authoritative comparisons,
- local rule-source changes alter effective policy identity,
- Python and TypeScript agree on shared fixtures,
- dashboard live and upload modes produce the same improvement semantics,
- existing stats fields remain backward compatible, and
- confounded baseline/candidate selections suppress the aggregate headline.
