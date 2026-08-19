---
name: dashboard
description: "Skill for the Dashboard area of slopgate. 234 symbols across 25 files."
---

# Dashboard

234 symbols | 25 files | Cohesion: 81%

## When to Use

- Working with code in `dashboard/`
- Understanding how projectTrees, getSorted, nonSlopgateTree work
- Modifying dashboard-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `dashboard/src/components/dashboard/SessionTimeline.tsx` | outputRecord, hasDirectToolInputFields, toolInputFromOutput, candidatePathsFromInput, nestedInputRecords (+84) |
| `dashboard/src/components/dashboard/PathExplorer.tsx` | isValidPath, createPathNode, eventKey, findingKey, sortAlpha (+29) |
| `dashboard/src/components/dashboard/SessionExplorer.tsx` | toggleSetValue, SessionExplorer, copyId, resetSessionPaging, FilterGroup (+11) |
| `tests/dashboard/test_forcedash_snapshot_summary.py` | run_trace_snapshot_script, write_event_log, projected_event, test_trace_snapshot_script_preserves_pi_platform, test_trace_snapshot_script_preserves_lineage_metadata_aliases (+7) |
| `tests/dashboard/test_forcedash_harness_status.py` | _run_harness_status_with_fake_opencode_config, _opencode_platform, _codex_platform, _pi_platform, _write_codex_install (+6) |
| `dashboard/src/lib/sessionHelpers.ts` | isBlockingDecision, isAdvisoryDecision, isBetterCauseCandidate, getPathsForFinding, primarySessionCause (+3) |
| `dashboard/src/lib/ruleCalibration.ts` | stableValue, resultScopeKey, findingsForRule, asymptoticRatio, recurrenceScore (+1) |
| `dashboard/src/components/dashboard/DecisionFunnel.tsx` | formatAxisLabel, formatCompactCount, formatEventLabel, getPipelineCellClass, buildLanePoints (+1) |
| `dashboard/src/components/dashboard/FalsePositiveAnalysis.tsx` | signals, lensLabel, lensName, FalsePositiveAnalysis, SummaryCard |
| `dashboard/src/components/dashboard/FileDropZone.tsx` | formatLastEvent, formatTraceTimestamp, FileDropZone, handleFiles, handleDrop |

## Entry Points

Start here when exploring this area:

- **`projectTrees`** (Function) — `dashboard/src/components/dashboard/PathExplorer.tsx:929`
- **`getSorted`** (Function) — `dashboard/src/components/dashboard/PathExplorer.tsx:933`
- **`nonSlopgateTree`** (Function) — `dashboard/src/components/dashboard/PathExplorer.tsx:955`
- **`entries`** (Function) — `dashboard/src/components/dashboard/SessionTimeline.tsx:1029`
- **`test_harness_status_checks_live_opencode_config_and_redacts_provider_secret`** (Function) — `tests/dashboard/test_forcedash_harness_status.py:96`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `projectTrees` | Function | `dashboard/src/components/dashboard/PathExplorer.tsx` | 929 |
| `getSorted` | Function | `dashboard/src/components/dashboard/PathExplorer.tsx` | 933 |
| `nonSlopgateTree` | Function | `dashboard/src/components/dashboard/PathExplorer.tsx` | 955 |
| `entries` | Function | `dashboard/src/components/dashboard/SessionTimeline.tsx` | 1029 |
| `test_harness_status_checks_live_opencode_config_and_redacts_provider_secret` | Function | `tests/dashboard/test_forcedash_harness_status.py` | 96 |
| `test_harness_status_accepts_current_codex_hooks_feature_key` | Function | `tests/dashboard/test_forcedash_harness_status.py` | 117 |
| `test_pi_harness_status_missing` | Function | `tests/dashboard/test_forcedash_harness_status.py` | 134 |
| `test_pi_harness_status_partial` | Function | `tests/dashboard/test_forcedash_harness_status.py` | 142 |
| `test_pi_harness_status_disabled` | Function | `tests/dashboard/test_forcedash_harness_status.py` | 154 |
| `test_pi_harness_status_installed` | Function | `tests/dashboard/test_forcedash_harness_status.py` | 170 |
| `findFirstVisibleRow` | Function | `dashboard/src/components/dashboard/sessionExplorerAnchoring.ts` | 3 |
| `determineAnchor` | Function | `dashboard/src/components/dashboard/sessionExplorerAnchoring.ts` | 16 |
| `calculateScrollAdjustment` | Function | `dashboard/src/components/dashboard/sessionExplorerAnchoring.ts` | 42 |
| `SessionExplorer` | Function | `dashboard/src/components/dashboard/SessionExplorer.tsx` | 182 |
| `copyId` | Function | `dashboard/src/components/dashboard/SessionExplorer.tsx` | 315 |
| `resetSessionPaging` | Function | `dashboard/src/components/dashboard/SessionExplorer.tsx` | 321 |
| `filteredEvents` | Function | `dashboard/src/components/dashboard/PathExplorer.tsx` | 802 |
| `filteredRules` | Function | `dashboard/src/components/dashboard/PathExplorer.tsx` | 813 |
| `PathExplorer` | Function | `dashboard/src/components/dashboard/PathExplorer.tsx` | 779 |
| `getProjectInfo` | Function | `dashboard/src/components/dashboard/PathExplorer.tsx` | 866 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `App → HasTraceIdentity` | cross_community | 6 |
| `RenderDetailPane → NormalizePatchPath` | cross_community | 5 |
| `RenderDetailPane → IsApplyPatchText` | cross_community | 4 |
| `App → Cn` | cross_community | 4 |
| `App → LatestTimestamp` | cross_community | 4 |
| `App → BuildRecordKeySet` | cross_community | 4 |
| `App → CountBoolMapDiffs` | cross_community | 4 |
| `Dashboard → FormatLastEvent` | cross_community | 3 |
| `Dashboard → FormatTraceTimestamp` | cross_community | 3 |
| `Dashboard → Cn` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Ui | 26 calls |
| Rules | 5 calls |
| Context | 3 calls |
| Hooks | 2 calls |

## How to Explore

1. `context({name: "projectTrees"})` — see callers and callees
2. `query({search_query: "dashboard"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
