HANDOFF CONTEXT
===============

USER REQUESTS (AS-IS)
---------------------
- "Implement this plan: Slopgate Feedback-Loop Improvement Plan"
- "continue"
- "Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed."
- "is it trending upward at least? I'd like to merge the branch back to master but not promote it to the remote repo and pypl"
- "Can you create a handoff document that can inform the next session of our tracking and progress and targets"

GOAL
----
Finish the feedback-loop acceptance audit, safely commit the reviewed branch, and merge it into local master without pushing, publishing, or enabling unsupported blocking promotion.

WORK COMPLETED
--------------
- I implemented the state-backed First-Write Contract with normalized session/target identity, required contract fields, expiry/schema handling, target-specific denial, and single-use mutation consumption.
- I implemented projected pre-edit lint using reconstructable content only, isolated mirrored overlays, touched collectors, real-path restoration, cleanup guarantees, advisory fallback, and authoritative post-edit lint.
- I implemented semantic retry budgeting with exact diagnostic fingerprints, semantic churn identities, path/rule isolation, third-attempt `RETRY-BUDGET-001` enforcement, and structured changed-design recovery evidence.
- I replaced keyword-only recovery unlocking with persisted records, successful read-after-lock proof, session/repository checks, material-design comparison, expiry, and consumption.
- I implemented the opt-in aggregate repository failure profile with privacy-safe decayed counts, deterministic pruning/caps, inspection/reset CLI surfaces, and bounded recurring-risk guidance.
- I added rule-specific recovery guidance and recommendation-gate coverage.
- I completed the 100-record `PY-LOG-002` evidence gate without changing rule behavior: 19 true positives, 64 false positives, and 17 needing context, with agreement, adjudication, and replay artifacts.
- I corrected two confirmed `PY-CODE-012` advisory false positives in test paths and retained production feature-envy findings.
- I hardened installer lifecycle behavior, made auto-update explicit opt-in, pinned the default updater source, added atomic/symlink-safe writes, and preserved conservative platform capability claims.
- I installed and exercised live Claude, Codex, Cursor, OpenCode, and Pi hook surfaces in advisory/capability-gated mode.
- I added a top-level verification summary and corrected the public retry-budget template wording: `deny` blocks, `context` is advisory, and `enabled = false` disables it.

CURRENT STATE
-------------
- Current worktree: `/home/trav/.local/share/opencode/worktree/245381924f02e80d26d571167f959abe7db7e928/clever-koala`.
- Current branch: `clever-koala`.
- Local master worktree: `/home/trav/.openclaw/workspace-hooker/slopgate`.
- `HEAD`, `master`, and `clever-koala` all currently point to `8410d10b05e7e2c0776344236b6d579a270610be`; the feedback-loop implementation is not committed yet.
- The implementation and evidence changes are currently staged: 127 files, about 14,144 insertions and 739 deletions.
- Three generated runtime files are also staged and should not be included blindly in the implementation commit: `logs/failure-profiles/b2fa239366c32d875cbd22e5f159449d36c468ba4e2954deaeb109135aa9f226.json.lock`, `logs/hook-state.json`, and `logs/hook-state.lock`.
- No upstream is configured for `clever-koala`.
- The requested local merge into master has not been performed. Nothing has been pushed, published, released, or uploaded to PyPI.
- Latest fresh seven-day stats at `2026-07-16T22:22:08Z`: 160,692 raw events, 160,690 analyzed events, 346 sessions, FTR `0.7268`.
- Latest fresh one-day stats: 48,090 raw events, 48,088 analyzed events, 7 sessions, FTR `0.7717`.
- Baseline FTR is `0.702`; the Phase 6 target is `0.902`. The seven-day trend is upward by 2.48 percentage points, but remains 17.52 points below the target.
- Phase 4 remains in progress because live denials have not been sufficiently labeled for a precision exit. The current rollout artifact still records 1 labeled blocking true positive, 2 corrected advisory false positives, and `precision_sample_sufficient = false`.
- Phase 6 is not met and blocking promotion remains disabled.
- Phase 7 is complete: the `PY-LOG-002` audit decision, classifications, agreement, adjudication, and replay evidence exist, while current rule behavior remains unchanged.
- Earlier full validation passed with 2,265 tests and 8 skips. The most recent focused validation passed 108 tests total, `slopgate lint check --details` was clean, template TOML parsed, and CLI `lint init` happy/help/existing-file paths worked.
- TOML LSP diagnostics are unavailable in this environment; parser validation was used instead.
- The last GitNexus change analysis classified the broad branch as CRITICAL risk because it spans core runtime, state, installer, adapter, and rule flows. Rerun it before committing because the staged set has continued to change.

PENDING TASKS
-------------
- Inspect the staged diff in full and separate any unrelated or generated runtime artifacts before committing. In particular, unstage the three `logs/` runtime state/lock files unless there is an explicit reason to version them.
- Refresh `docs/evidence/feedback-loop-current-state-2026-07-16.json`, `docs/evidence/feedback-loop-advisory-rollout-2026-07-16.json`, and `docs/evidence/feedback-loop-verification-summary-2026-07-16.json` from the latest `slopgate stats --days 7 --json` and `--days 1 --json` output if the commit should contain the newest metrics.
- Continue Phase 4 live precision work: identify and label post-rollout blocking/advisory findings, record canary duration and overhead, and define or apply a reproducible sample-sufficiency threshold before marking the phase complete.
- Continue Phase 6 observation. Do not enable blocking promotion unless seven-day FTR reaches at least `0.902` and confirmed-rule precision has no regression.
- Run `gitnexus_detect_changes()` immediately before committing and explicitly review its CRITICAL-risk affected flows.
- Re-run the full verification appropriate for the final staged contents, including `uv run pytest -q -n0`, `uv run slopgate lint check --details`, `slopgate test`, and the documented replay/CLI surfaces.
- Commit the branch locally using repository-style atomic commits. Then inspect the separate master worktree for dirtiness and merge the committed `clever-koala` branch into local `master`.
- Do not push master or the feature branch, do not create a remote PR, do not publish a release, and do not upload to PyPI.
- Active task: `T-c70ed337-4058-4a82-a156-83c10133af2c`, status `in_progress`, focus `Phase 4 live precision evidence`.

KEY FILES
---------
- `docs/evidence/feedback-loop-verification-summary-2026-07-16.json` - aggregate phase status, current decision, and source evidence list.
- `docs/evidence/feedback-loop-advisory-rollout-2026-07-16.json` - live canary precision, latency, error, and Phase 4/6 state.
- `docs/evidence/feedback-loop-current-state-2026-07-16.json` - measured seven-day FTR and promotion target.
- `docs/evidence/feedback-loop-py-log-002-adjudication-2026-07-16.json` - final `PY-LOG-002` classification decision.
- `src/slopgate/rules/first_write_contract.py` - pre-edit contract rule and rollout behavior.
- `src/slopgate/rules/projected_lint/` - projection, overlay, collector, parity, and rollout implementation.
- `src/slopgate/engine/_retry/` - retry identity, budget, steering, and rule-specific guidance.
- `src/slopgate/state/retry/` - retry and structured recovery persistence/evidence.
- `src/slopgate/failure_profile/` - aggregate profile capture, storage, pruning, and guidance.
- `docs/cutover.md` - rollout, promotion, capability, and rollback instructions.

IMPORTANT DECISIONS
-------------------
- First-write contracts and projected lint default to shadow/advisory rollout and are promoted independently through existing rule-surface configuration.
- Semantic retry preserves its blocking posture by default but can be changed to advisory or disabled without deleting trace history.
- `QUALITY-LINT-001` remains the authoritative post-edit backstop when projected content is missing or incomplete.
- Aggregate failure profiles are explicit per-repository opt-in and store only allowed aggregate dimensions; feedback-loop meta rules are excluded from steering to avoid circular recommendations.
- `PY-LOG-002` behavior remains unchanged despite the completed audit; evidence documents the decision and locks the current boundary.
- Platform claims remain capability-gated: Claude is the richest surface, Cursor/Codex/Pi are partial, and OpenCode is plugin-mediated/degraded where hard enforcement is unavailable.
- Operational Phase 4 and Phase 6 acceptance is separate from implementation completeness. The branch may be merged locally while promotion remains disabled.
- The observed FTR trend is positive but weak; it is evidence for continued canary observation, not for promotion.

EXPLICIT CONSTRAINTS
--------------------
- "plan already agreed; implement it end-to-end without deviating it."
- "but not promote it to the remote repo and pypl"
- "Keep README aligned with upstream docs; prefer \"partial\"/\"best-effort\" over parity claims."
- "`slopgate install` owns harness hook wiring; bundle fragments merge, never symlink over CLAUDE.md."
- "MUST run `gitnexus_detect_changes()` before committing"
- "Never delete failing tests to get a green build. Never weaken a test to make it pass."
- "Never use destructive git commands (`reset --hard`, `checkout --`, force-push) without explicit approval."

CONTEXT FOR CONTINUATION
------------------------
- Treat the worktree and live trace corpus as authoritative; evidence JSON files are snapshots and can become stale as traffic continues.
- A rising raw denial count does not satisfy Phase 4 by itself. Only reviewed/labeled post-rollout findings establish precision.
- The latest live metrics are newer than the current evidence JSON fields. Refresh deliberately and keep timestamps/denominators reproducible.
- Before local merge, confirm the master worktree is clean. Because master is checked out elsewhere, commit on `clever-koala` first and perform the merge from `/home/trav/.openclaw/workspace-hooker/slopgate`.
- Preserve all trace history and keep blocking promotion disabled during the local merge.
- Do not interpret the CRITICAL GitNexus risk label as a reason to abandon the merge; it means the staged diff needs deliberate review and full verification because core execution flows are affected.
