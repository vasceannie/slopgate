## 1. Conclusion

Slopgate already records enough runtime evaluation data to build a useful **deterministic improvement-measurement layer without transcript mining or an LLM**. `results.jsonl` carries session, repo/enforcement mode, platform capability, model/provider, tool input, mutation intent, findings, errors, and timings. `slopgate stats` already loads that file as its canonical source. `src/slopgate/engine/_evaluation.py:139-153`, `src/slopgate/engine/_evaluation.py:175-196`, `src/slopgate/stats/_load.py:13-34`, `src/slopgate/stats/_report.py:160-182`

The problem is that Slopgate currently has several incompatible definitions of “improved.” Python stats call a one-off denial “first-time resolved,” dashboard operational metrics treat any later non-blocking event as resolution, and rule calibration uses a comparable-attempt key that contains the entire `tool_input`, so an actual repaired write can cease to be comparable merely because, scandalously, the code changed. `src/slopgate/stats/_analysis.py:164-177`, `dashboard/src/hooks/useTraceData.ts:1091-1136`, `dashboard/src/lib/ruleCalibration.ts:54-61`

I would implement a **canonical repair-episode model inside the existing stats layer first**, then add policy/version fingerprints, baseline-vs-candidate comparisons, and finally make the dashboard consume those semantics. Your uploaded feedback-loop design is directionally right about episode-based deterministic metrics and cohort comparisons; the repo inspection suggests that first layer can be substantially simpler than the eventual cross-harness transcript system. 

## 2. Findings

| Severity | Type                 | Finding                                                                                                                                                     | Evidence                                                                                                                                                                                                    | Why it matters                                                                                                                                       | Recommended fix                                                                                                                     |
| -------- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| **P1**   | `confirmed behavior` | `first_time_resolution_rate` does not actually observe resolution. A `(session, rule, path)` seen exactly once is immediately counted as resolved.          | `src/slopgate/stats/_analysis.py:164-177`, `src/slopgate/stats/_analysis.py:190-192`, `src/slopgate/stats/_report.py:141-157`                                                                               | A lower repeat count can masquerade as successful remediation even when the agent abandoned the issue.                                               | Preserve it temporarily as a legacy churn metric, but introduce episode-based `repair_success_rate` and `first_attempt_clean_rate`. |
| **P1**   | `confirmed behavior` | Dashboard session resolution is too broad: after the first deny/block, **any** later allow/context/warn/info marks the session resolved.                    | `dashboard/src/hooks/useTraceData.ts:1091-1136`                                                                                                                                                             | An unrelated Read/Bash/other-file operation can “resolve” a failed write statistically.                                                              | Replace dashboard resolution with the same canonical repair-episode evaluator used by stats.                                        |
| **P1**   | `confirmed behavior` | `results.jsonl` intentionally omits `candidate_paths` and `languages`, even though the corresponding event trace contains them.                             | `src/slopgate/engine/_evaluation.py:156-172`, `src/slopgate/engine/_evaluation.py:175-196`, `dashboard/src/context/traceRecordValidation.ts:34-47`                                                          | The canonical stats input cannot reliably group repairs by target or stratify by language without joining another stream or reparsing tool payloads. | Add `candidate_paths` and `languages` to `_payload_for_done()`.                                                                     |
| **P1**   | `confirmed behavior` | Result traces have no effective policy/intervention fingerprint.                                                                                            | `src/slopgate/engine/_evaluation.py:175-196`                                                                                                                                                                | Before/after numbers cannot prove which rule/config/prompt revision was active.                                                                      | Trace Slopgate version plus deterministic effective-policy and guidance fingerprints.                                               |
| **P2**   | `confirmed behavior` | Calibration's “comparable result” key hashes the full `tool_input`.                                                                                         | `dashboard/src/lib/ruleCalibration.ts:54-61`                                                                                                                                                                | A Write/Edit repair commonly changes the content, causing the repaired attempt to fall into another scope.                                           | Introduce a content-independent `repair_scope_key`: repo + session + rule + event/tool + normalized target paths.                   |
| **P2**   | `confirmed behavior` | Improvement logic is split between Python stats, dashboard calibration, and dashboard session ops.                                                          | `src/slopgate/stats/_analysis.py:131-192`, `dashboard/src/lib/ruleCalibration.ts:17-40`, `dashboard/src/components/dashboard/FalsePositiveAnalysis.tsx:42`, `dashboard/src/hooks/useTraceData.ts:1091-1136` | The same trace history can produce three different stories about whether behavior improved.                                                          | Put canonical semantics in Python and make CLI/dashboard presentations consume or mirror one tested contract.                       |
| **P2**   | `confirmed behavior` | Current enforcement already correctly distinguishes strict managed-repo rules from safety-only behavior, but raw aggregate metrics can erase that boundary. | `src/slopgate/engine/_runner.py:229-267`, `src/slopgate/rules/__init__.py:228-259`, `tests/engine/test_12_enforcement_modes.py:33-111`                                                                      | Mixing `repo_strict`, `repo_relaxed`, and `outside_repo` can make an enforcement change look like an agent-quality improvement.                      | Default coding-improvement analysis to `repo_strict`; report relaxed/outside-repo cohorts separately.                               |

One boundary is **Unverified**: if by “evaluation data” you specifically mean the output of `make eval-dataset-ats`, GitNexus exposes a test showing that target invocation is allowed, but it did not expose the target's implementation or output schema. `tests/test_shell_read_rules_public_api.py:127-143`. The plan below therefore targets Slopgate's canonical runtime evaluation data in `results.jsonl`.

---

## 3. Detailed analysis and implementation plan

### A. Define one canonical unit: the repair episode

Do not start by adding more percentages to `_analysis.py`. That merely gives the metric hydra another head.

The current stats layer groups denials by `(session, rule_id, path)`, but only counts occurrences; it does not inspect a later clean attempt. `src/slopgate/stats/_analysis.py:164-177` The dashboard has the better idea of comparing attempts, but its scope key contains command plus the full stable `tool_input`. `dashboard/src/lib/ruleCalibration.ts:54-61`

I would add:

```text
src/slopgate/stats/
├── _episodes.py
├── _improvement.py
└── _fingerprints.py
```

Keep this under `stats` initially rather than founding another architectural kingdom. The existing loader, report path, JSON mode, and CLI integration are already there. `src/slopgate/stats/_load.py:50-71`, `src/slopgate/stats/_report.py:160-182`, `src/slopgate/cli/parsers.py:266-299`

A rule-specific repair scope should conceptually be:

```text
session_id
+ resolved_repo_root
+ enforcement_mode
+ rule_id
+ event/tool family
+ normalized candidate path(s)
```

It should **not** contain source content. For pathless rules, record `scope_confidence="low"` rather than pretending the correlation is equally precise.

An episode becomes:

```text
first relevant attempt
→ first block/deny
→ zero or more comparable attempts
→ first comparable clean attempt
```

Possible terminal states should be explicit:

```text
never_blocked
resolved
still_failing
no_observed_followup
```

I would deliberately call the last state `no_observed_followup`, not “abandoned.” The trace proves absence of a later comparable result, not the psychological state of the agent. Humans have invented enough telemetry fan fiction already.

### B. Metrics worth extracting in v1

The result payload already records `mutating`, timing, model/provider, enforcement mode, repo, platform capability, findings and errors. `src/slopgate/engine/_evaluation.py:139-153`, `src/slopgate/engine/_evaluation.py:175-196`

That supports these metrics without external histories:

1. **Blocking evaluations per 100 mutating evaluations**
   `100 × mutating evaluations ending deny/block / mutating evaluations`

2. **First-attempt clean rate**
   Percentage of repair scopes whose first mutating attempt does not produce an enforcing finding.

3. **Observed repair success rate**
   Blocked episodes with a later comparable clean attempt divided by blocked episodes with adequate observable follow-up. Keep `no_observed_followup` visible rather than silently treating it as success or failure.

4. **Repair attempts**
   Median and p90 attempts between initial block and clean comparable attempt.

5. **Repair latency**
   Median and p90 elapsed wall-clock time between initial block and clean comparable attempt.

6. **Persistence rate by rule**
   How often the same rule remains present on later comparable attempts. This replaces the current crude repeated-denial interpretation and generalizes the useful idea in dashboard calibration. `dashboard/src/lib/ruleCalibration.ts:17-40`, `dashboard/src/lib/ruleCalibration.ts:90`

7. **Runtime reliability**
   Result error rate plus p50/p95 `evaluation_ms` and `rule_engine_ms`; those timing fields are already emitted on every completed evaluation. `src/slopgate/engine/_evaluation.py:199-240`

8. **Cohort facets**
   Repo, enforcement mode, platform/capability, model/provider, rule, event/tool, and once the trace is enriched, language and policy fingerprint. The underlying dimensions already exist except the missing result-level language/path and fingerprints. `src/slopgate/engine/_evaluation.py:139-196`

Do **not** produce a single “Slopgate improvement score.” A 12% reduction in blocks can mean the agent got better, the rule got weaker, a repo was disabled, a different model was used, or somebody simply stopped doing the thing being measured. One scalar would hide exactly the information this feature is supposed to extract.

### C. Fix the result trace before running serious experiments

There are two small but high-value schema changes.

First, mirror `candidate_paths` and `languages` from the start record into the result record. They exist at evaluation start but are deliberately absent from result rows today. `src/slopgate/engine/_evaluation.py:156-172`, `src/slopgate/engine/_evaluation.py:175-196`, `dashboard/src/context/traceRecordValidation.ts:34-47`

Change `_payload_for_done()` to include:

```python
"candidate_paths": ctx.candidate_paths,
"languages": sorted(ctx.languages),
```

This keeps `results.jsonl` self-sufficient for the stats pipeline instead of requiring an events/results join merely to answer “what file was this repair about?”

Second, add provenance such as:

```text
slopgate_version
effective_policy_fingerprint
guidance_fingerprint
```

`effective_policy_fingerprint` should represent the effective enforcement configuration, not raw config text. At minimum it should change when effective rule enablement, surface action, severity override, or other enforcement-relevant policy changes.

There is already precedent for deterministic hashing in the lint project-index fingerprint, which hashes engine/version/config-derived state rather than relying on timestamps. `src/slopgate/lint/project_index/fingerprint.py:38-54`

The trace should store the hash, not secret-bearing raw configuration.

### D. Baseline vs candidate comparisons

Once provenance exists, add an improvement comparison object:

```text
ImprovementComparison
  baseline
  candidate
  dimensions
  metric_deltas
  sample_counts
```

A comparison should produce both absolute and relative deltas:

```text
first_attempt_clean_rate: 71% → 82%  (+11 pp)
blocking_per_100_mutations: 24.1 → 15.8  (-34%)
median_repair_attempts: 2 → 1
repair_success_rate: 78% → 91%
evaluation_p95_ms: 146 → 151  (+3%)
```

The important part is the cohort contract. Do not compare two windows unless the report can show their distribution across repo, enforcement mode, platform/capability, rule, and ideally model/provider. Those fields are already present in result traces. `src/slopgate/engine/_evaluation.py:139-196`

Once fingerprints exist, `effective_policy_fingerprint` becomes a first-class cohort dimension. That lets you answer the actually useful question:

> Did policy/guidance revision B reduce preventable repair churn relative to A under comparable workloads?

instead of:

> Number went down this week, everybody celebrate.

### E. Preserve old metrics, but stop calling them outcomes

I would not silently change the implementation behind the existing `first_time_resolution_rate` key. Existing scripts or consumers may rely on it.

Instead:

* Mark `first_time_resolution_rate` as legacy/deprecated.
* Add an accurately named equivalent such as `single_deny_scope_rate`.
* Introduce `repair_success_rate` as the outcome-valid successor.
* Print a deprecation explanation in the human-readable stats report.

The reason is concrete: current logic increments `first_time_resolved` solely because count is `<= 1`. `src/slopgate/stats/_analysis.py:164-177` Its current formula then presents that as resolution. `src/slopgate/stats/_analysis.py:190-192`

### F. CLI integration

The narrowest UI is to extend `slopgate stats`, because it already owns the JSONL loader and JSON output. `src/slopgate/cli/commands.py:248-255`, `src/slopgate/cli/parsers.py:266-299`

I would land this progressively:

```text
slopgate stats --improvement --days 30
slopgate stats --improvement --days 30 --json
```

Then, after fingerprints have accumulated enough history:

```text
slopgate stats --improvement \
  --baseline-policy <hash-a> \
  --candidate-policy <hash-b>
```

The JSON output should expose raw counts alongside rates so downstream consumers do not have to reverse-engineer denominators from percentages.

### G. Consolidate the dashboard after the Python contract stabilizes

Do not immediately rewrite `ruleCalibration.ts`. Its existing persistence idea is useful, and `FalsePositiveAnalysis` currently consumes it directly. `dashboard/src/lib/ruleCalibration.ts:90`, `dashboard/src/components/dashboard/FalsePositiveAnalysis.tsx:42`

After the Python episode model has tests and fixtures:

1. Generate a shared fixture from representative result sequences.
2. Require Python improvement calculations and dashboard calculations to agree.
3. Replace the dashboard's broad session `resolutionRate` with episode-based resolution.
4. Replace or narrow `resultScopeKey()` so mutable source content is not part of repair identity.
5. Eventually treat TypeScript calibration as presentation/triage logic, not the authoritative definition of resolution.

This specifically removes the current case where any later non-blocking event counts as a blocked session resolving. `dashboard/src/hooks/useTraceData.ts:1091-1136`

### H. Test gates I would require

The core tests should encode semantics rather than merely chase the implementation:

```text
blocked write(path A, content v1)
→ clean write(path A, content v2)
= resolved in 1 repair attempt

blocked write(path A)
→ allowed bash/git status
= NOT resolved

blocked write(path A)
→ clean write(path B)
= NOT resolved

blocked rule X(path A)
→ clean attempt for rule X(path A)
= resolved

blocked rule X(path A)
→ rule Y(path A)
= X resolved only if comparable evaluation proves X absent

single block with no comparable follow-up
= no_observed_followup, NOT first-time resolved
```

That first test is particularly important because the existing dashboard scope key includes the complete `tool_input`, which would distinguish content v1 from v2. `dashboard/src/lib/ruleCalibration.ts:54-61`

### Recommended delivery order

**Slice 1: Outcome-correct metrics.** Add `_episodes.py` and `_improvement.py`, define content-independent repair scopes, add regression tests, and expose single-window metrics through `slopgate stats`. Keep existing fields intact. Existing loader and CLI seams are already suitable. `src/slopgate/stats/_load.py:50-71`, `src/slopgate/stats/_report.py:160-182`, `src/slopgate/cli/parsers.py:266-299`

**Slice 2: Trace completeness.** Add result-level `candidate_paths` and `languages`, then version/effective-policy fingerprints. The corresponding event fields already exist, so the former is a very small schema change. `src/slopgate/engine/_evaluation.py:156-196`

**Slice 3: Cohort comparison.** Add baseline/candidate reports keyed by policy fingerprint with deltas and raw sample counts, stratified by repo, harness capability, model/provider, rule, and language. The relevant runtime dimensions are already emitted. `src/slopgate/engine/_evaluation.py:139-196`

**Slice 4: Dashboard convergence.** Make dashboard resolution and rule persistence agree with the canonical episode semantics instead of maintaining separate outcome definitions. `dashboard/src/lib/ruleCalibration.ts:54-61`, `dashboard/src/hooks/useTraceData.ts:1091-1136`

**Slice 5: Causal transcript enrichment.** Only then add the broader transcript/agent-history layer from the uploaded design to answer *why* an improvement happened, rather than whether it happened. 

That order gets you credible numerical feedback quickly while keeping the much more invasive cross-harness conversation analysis optional.

## 4. Policy Boundary Recommendations

The metrics layer should preserve Slopgate's existing enforcement boundary rather than flattening every machine action into one giant “agent performance” bucket.

**Project repo work:** default improvement analysis to `enforcement_mode == "repo_strict"`. That is where Slopgate intentionally adds Git, quality, config, stop, LangGraph, Python AST, regex, and related coding guardrails. `src/slopgate/engine/_runner.py:242-267`, `src/slopgate/rules/__init__.py:228-259`

**General workstation use:** exclude `outside_repo` activity from coding-improvement KPIs by default. Current implementation deliberately runs the always-on safety set while withholding repo-strict coding rules outside enrolled repositories. That is a `confirmed behavior`, and tests explicitly defend it. `src/slopgate/engine/_runner.py:229-267`, `tests/engine/test_12_enforcement_modes.py:33-47`

**Server operations:** treat the same way as general workstation activity. Report narrow global-safety events and runtime health separately, but do not use fewer repo-quality findings during server administration as evidence that coding behavior improved. Current tests establish that even relaxed repositories retain safety protection while strict coding rules are suppressed. `tests/engine/test_12_enforcement_modes.py:91-111`

**Repo disable/skip semantics:** treat `repo_relaxed` and skipped strict paths as explicit cohort boundaries, not successes. A candidate policy that merely moves more traffic from `repo_strict` into relaxed/skipped modes should show that distribution change prominently instead of reporting a miraculous fall in violations. Enforcement mode is already resolved explicitly and written into result traces. `src/slopgate/engine/_runner.py:229-267`, `src/slopgate/engine/_evaluation.py:175-196`

Concretely, I would make the improvement analyzer default to **repo-strict only**, require an explicit flag to mix other modes, and refuse to calculate a single baseline/candidate delta across differing enforcement-mode distributions without showing the mode-specific breakdown. That keeps the measurement system aligned with Slopgate's current architecture instead of accidentally rewarding the easiest optimization known to software engineering: turning the guardrail off.
