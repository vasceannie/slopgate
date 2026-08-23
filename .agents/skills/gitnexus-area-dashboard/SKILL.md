---
name: gitnexus-area-dashboard
description: "Skill for the Dashboard area of slopgate. 234 symbols across 25 files."
---

# Dashboard

234 symbols | 25 files | Cohesion: 82%

## When to Use

- Working with code in `dashboard/`
- Understanding how renderDetailPane, TimelineVerdictStrip, correlationStatus work
- Modifying dashboard-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `dashboard/src/components/dashboard/SessionTimeline.tsx` | CodeBlock, FindingEvidenceBlock, FormattedOutputValue, PayloadPanel, PrettyJsonValue (+84) |
| `dashboard/src/components/dashboard/PathExplorer.tsx` | HeatmapView, PathExplorer, getProjectInfo, getRepoEnforcementMode, handleRemoveSkipPath (+31) |
| `dashboard/src/components/dashboard/SessionExplorer.tsx` | FilterChip, FilterGroup, MultiSelectMenu, SessionExplorer, copyId (+11) |
| `tests/dashboard/test_forcedash_snapshot_summary.py` | base_event, test_trace_snapshot_script_defaults_missing_platform_to_unknown, test_trace_snapshot_script_normalizes_unsupported_platform_to_unknown, test_trace_snapshot_script_preserves_cursor_platform, test_trace_snapshot_script_preserves_pi_platform (+7) |
| `tests/dashboard/test_forcedash_harness_status.py` | _codex_platform, _opencode_platform, _pi_platform, _run_harness_status_with_fake_opencode_config, _write_codex_install (+6) |
| `dashboard/src/lib/sessionHelpers.ts` | correlationStatus, getPathsForFinding, isAdvisoryDecision, isBetterCauseCandidate, isBlockingDecision (+3) |
| `dashboard/src/components/dashboard/DecisionFunnel.tsx` | DecisionFunnel, buildLanePoints, formatAxisLabel, formatCompactCount, formatEventLabel (+1) |
| `dashboard/src/components/dashboard/FalsePositiveAnalysis.tsx` | signals, FalsePositiveAnalysis, SummaryCard, lensLabel, lensName |
| `dashboard/src/components/dashboard/FileDropZone.tsx` | FileDropZone, handleDrop, handleFiles, formatLastEvent, formatTraceTimestamp |
| `tests/dashboard/test_forcedash_server.py` | _write_next_line_from_reader, test_streaming_idle_pipe_does_not_block_waiting_for_next_line, close, _TailProcess, _TimeoutTailProcess |

## Entry Points

Start here when exploring this area:

- **`renderDetailPane`** (Function) — `dashboard/src/components/dashboard/SessionTimeline.tsx:1334`
- **`TimelineVerdictStrip`** (Function) — `dashboard/src/components/dashboard/TimelineVerdictStrip.tsx:9`
- **`correlationStatus`** (Function) — `dashboard/src/lib/sessionHelpers.ts:379`
- **`entries`** (Function) — `dashboard/src/components/dashboard/SessionTimeline.tsx:1029`
- **`test_harness_status_accepts_current_codex_hooks_feature_key`** (Function) — `tests/dashboard/test_forcedash_harness_status.py:117`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `renderDetailPane` | Function | `dashboard/src/components/dashboard/SessionTimeline.tsx` | 1334 |
| `TimelineVerdictStrip` | Function | `dashboard/src/components/dashboard/TimelineVerdictStrip.tsx` | 9 |
| `correlationStatus` | Function | `dashboard/src/lib/sessionHelpers.ts` | 379 |
| `entries` | Function | `dashboard/src/components/dashboard/SessionTimeline.tsx` | 1029 |
| `test_harness_status_accepts_current_codex_hooks_feature_key` | Function | `tests/dashboard/test_forcedash_harness_status.py` | 117 |
| `test_harness_status_checks_live_opencode_config_and_redacts_provider_secret` | Function | `tests/dashboard/test_forcedash_harness_status.py` | 96 |
| `test_pi_harness_status_disabled` | Function | `tests/dashboard/test_forcedash_harness_status.py` | 154 |
| `test_pi_harness_status_installed` | Function | `tests/dashboard/test_forcedash_harness_status.py` | 170 |
| `test_pi_harness_status_missing` | Function | `tests/dashboard/test_forcedash_harness_status.py` | 134 |
| `test_pi_harness_status_partial` | Function | `tests/dashboard/test_forcedash_harness_status.py` | 142 |
| `SessionExplorer` | Function | `dashboard/src/components/dashboard/SessionExplorer.tsx` | 182 |
| `copyId` | Function | `dashboard/src/components/dashboard/SessionExplorer.tsx` | 315 |
| `resetSessionPaging` | Function | `dashboard/src/components/dashboard/SessionExplorer.tsx` | 321 |
| `calculateScrollAdjustment` | Function | `dashboard/src/components/dashboard/sessionExplorerAnchoring.ts` | 42 |
| `determineAnchor` | Function | `dashboard/src/components/dashboard/sessionExplorerAnchoring.ts` | 16 |
| `findFirstVisibleRow` | Function | `dashboard/src/components/dashboard/sessionExplorerAnchoring.ts` | 3 |
| `PathExplorer` | Function | `dashboard/src/components/dashboard/PathExplorer.tsx` | 779 |
| `getProjectInfo` | Function | `dashboard/src/components/dashboard/PathExplorer.tsx` | 867 |
| `getRepoEnforcementMode` | Function | `dashboard/src/components/dashboard/PathExplorer.tsx` | 999 |
| `handleRemoveSkipPath` | Function | `dashboard/src/components/dashboard/PathExplorer.tsx` | 1070 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `App → IsEventName` | cross_community | 7 |
| `App → HasTraceIdentity` | cross_community | 6 |
| `App → IsStringArray` | cross_community | 6 |
| `App → NormalizePlatform` | cross_community | 6 |
| `RenderDetailPane → NormalizePatchPath` | cross_community | 5 |
| `App → BuildRecordKeySet` | cross_community | 4 |
| `App → LatestTimestamp` | cross_community | 4 |
| `SessionOutcomeSummary → IsAdvisoryDecision` | cross_community | 4 |
| `SessionOutcomeSummary → IsBetterCauseCandidate` | cross_community | 4 |
| `SessionOutcomeSummary → IsBlockingDecision` | cross_community | 4 |

## How to Explore

1. `context({name: "renderDetailPane"})` — see callers and callees
2. `query({search_query: "dashboard"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
