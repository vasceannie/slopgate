---
name: gitnexus-area-context
description: "Skill for the Context area of slopgate. 70 symbols across 8 files."
---

# Context

70 symbols | 8 files | Cohesion: 90%

## When to Use

- Working with code in `dashboard/`
- Understanding how classifyLine, coerceTraceRecord, TimeWindowSelector work
- Modifying context-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `dashboard/src/context/traceRecordValidation.ts` | aliasedValue, classifyLine, coerceTraceRecord, hasTraceIdentity, isEventName (+22) |
| `dashboard/src/context/TraceDataContext.tsx` | TraceDataProvider, latestDataAt, buildRecordKeySet, buildTraceDataKeys, getInitialData (+13) |
| `dashboard/src/context/RulesConfigContext.tsx` | RulesConfigProvider, discardChanges, saveConfig, cloneConfig, countBoolMapDiffs (+3) |
| `dashboard/src/context/TraceDataContext.test.ts` | DataIdentityProbe, RuleCountProbe, SnapshotSummaryProbe, SourceActionProbe, SourceStateProbe (+2) |
| `dashboard/src/context/FlagContext.tsx` | addFlag, removeFlag, resolveFlag, unresolveFlag, saveFlags |
| `dashboard/src/components/dashboard/TimeWindowSelector.tsx` | TimeWindowSelector, setTimeWindow, togglePlatform |
| `dashboard/src/lib/improvement.test.ts` | normalizeResults |
| `dashboard/src/context/useTraceDataSource.ts` | useTraceDataSource |

## Entry Points

Start here when exploring this area:

- **`classifyLine`** (Function) — `dashboard/src/context/traceRecordValidation.ts:33`
- **`coerceTraceRecord`** (Function) — `dashboard/src/context/traceRecordValidation.ts:406`
- **`TimeWindowSelector`** (Function) — `dashboard/src/components/dashboard/TimeWindowSelector.tsx:35`
- **`setTimeWindow`** (Function) — `dashboard/src/components/dashboard/TimeWindowSelector.tsx:47`
- **`togglePlatform`** (Function) — `dashboard/src/components/dashboard/TimeWindowSelector.tsx:38`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `classifyLine` | Function | `dashboard/src/context/traceRecordValidation.ts` | 33 |
| `coerceTraceRecord` | Function | `dashboard/src/context/traceRecordValidation.ts` | 406 |
| `TimeWindowSelector` | Function | `dashboard/src/components/dashboard/TimeWindowSelector.tsx` | 35 |
| `setTimeWindow` | Function | `dashboard/src/components/dashboard/TimeWindowSelector.tsx` | 47 |
| `togglePlatform` | Function | `dashboard/src/components/dashboard/TimeWindowSelector.tsx` | 38 |
| `useTraceDataSource` | Function | `dashboard/src/context/useTraceDataSource.ts` | 3 |
| `RulesConfigProvider` | Function | `dashboard/src/context/RulesConfigContext.tsx` | 72 |
| `discardChanges` | Function | `dashboard/src/context/RulesConfigContext.tsx` | 234 |
| `saveConfig` | Function | `dashboard/src/context/RulesConfigContext.tsx` | 206 |
| `TraceDataProvider` | Function | `dashboard/src/context/TraceDataContext.tsx` | 162 |
| `latestDataAt` | Function | `dashboard/src/context/TraceDataContext.tsx` | 408 |
| `ingestFiles` | Function | `dashboard/src/context/TraceDataContext.tsx` | 316 |
| `refreshSnapshot` | Function | `dashboard/src/context/TraceDataContext.tsx` | 276 |
| `replaceData` | Function | `dashboard/src/context/TraceDataContext.tsx` | 185 |
| `resetToMock` | Function | `dashboard/src/context/TraceDataContext.tsx` | 383 |
| `addFlag` | Function | `dashboard/src/context/FlagContext.tsx` | 22 |
| `removeFlag` | Function | `dashboard/src/context/FlagContext.tsx` | 38 |
| `resolveFlag` | Function | `dashboard/src/context/FlagContext.tsx` | 46 |
| `unresolveFlag` | Function | `dashboard/src/context/FlagContext.tsx` | 54 |
| `appendRecord` | Function | `dashboard/src/context/TraceDataContext.tsx` | 190 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `App → IsEventName` | cross_community | 7 |
| `App → HasTraceIdentity` | cross_community | 6 |
| `App → IsStringArray` | cross_community | 6 |
| `App → NormalizePlatform` | cross_community | 6 |
| `TraceDataProvider → IsEventName` | cross_community | 6 |
| `TraceDataProvider → IsStringArray` | cross_community | 6 |
| `TraceDataProvider → HasTraceIdentity` | cross_community | 5 |
| `TraceDataProvider → NormalizePlatform` | cross_community | 5 |
| `App → BuildRecordKeySet` | cross_community | 4 |
| `App → LatestTimestamp` | cross_community | 4 |

## How to Explore

1. `context({name: "classifyLine"})` — see callers and callees
2. `query({search_query: "context"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
