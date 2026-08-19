---
name: context
description: "Skill for the Context area of slopgate. 69 symbols across 7 files."
---

# Context

69 symbols | 7 files | Cohesion: 84%

## When to Use

- Working with code in `dashboard/`
- Understanding how classifyLine, coerceTraceRecord, TimeWindowSelector work
- Modifying context-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `dashboard/src/context/traceRecordValidation.ts` | hasTraceIdentity, classifyLine, isStringArray, optionalString, objectRecord (+22) |
| `dashboard/src/context/TraceDataContext.tsx` | latestTimestamp, latestTraceTimestamp, recordTimestamp, coerceSnapshotData, getInitialData (+13) |
| `dashboard/src/context/RulesConfigContext.tsx` | getBakedConfig, normalizeConfig, cloneConfig, countBoolMapDiffs, countPending (+3) |
| `dashboard/src/context/TraceDataContext.test.ts` | RuleCountProbe, DataIdentityProbe, SourceStateProbe, SnapshotSummaryProbe, SourceActionProbe (+2) |
| `dashboard/src/context/FlagContext.tsx` | saveFlags, addFlag, removeFlag, resolveFlag, unresolveFlag |
| `dashboard/src/components/dashboard/TimeWindowSelector.tsx` | TimeWindowSelector, togglePlatform, setTimeWindow |
| `dashboard/src/context/useTraceDataSource.ts` | useTraceDataSource |

## Entry Points

Start here when exploring this area:

- **`classifyLine`** (Function) — `dashboard/src/context/traceRecordValidation.ts:33`
- **`coerceTraceRecord`** (Function) — `dashboard/src/context/traceRecordValidation.ts:400`
- **`TimeWindowSelector`** (Function) — `dashboard/src/components/dashboard/TimeWindowSelector.tsx:35`
- **`togglePlatform`** (Function) — `dashboard/src/components/dashboard/TimeWindowSelector.tsx:37`
- **`setTimeWindow`** (Function) — `dashboard/src/components/dashboard/TimeWindowSelector.tsx:46`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `classifyLine` | Function | `dashboard/src/context/traceRecordValidation.ts` | 33 |
| `coerceTraceRecord` | Function | `dashboard/src/context/traceRecordValidation.ts` | 400 |
| `TimeWindowSelector` | Function | `dashboard/src/components/dashboard/TimeWindowSelector.tsx` | 35 |
| `togglePlatform` | Function | `dashboard/src/components/dashboard/TimeWindowSelector.tsx` | 37 |
| `setTimeWindow` | Function | `dashboard/src/components/dashboard/TimeWindowSelector.tsx` | 46 |
| `useTraceDataSource` | Function | `dashboard/src/context/useTraceDataSource.ts` | 3 |
| `RulesConfigProvider` | Function | `dashboard/src/context/RulesConfigContext.tsx` | 72 |
| `saveConfig` | Function | `dashboard/src/context/RulesConfigContext.tsx` | 206 |
| `discardChanges` | Function | `dashboard/src/context/RulesConfigContext.tsx` | 234 |
| `TraceDataProvider` | Function | `dashboard/src/context/TraceDataContext.tsx` | 162 |
| `refreshSnapshot` | Function | `dashboard/src/context/TraceDataContext.tsx` | 275 |
| `latestDataAt` | Function | `dashboard/src/context/TraceDataContext.tsx` | 408 |
| `replaceData` | Function | `dashboard/src/context/TraceDataContext.tsx` | 185 |
| `ingestFiles` | Function | `dashboard/src/context/TraceDataContext.tsx` | 315 |
| `resetToMock` | Function | `dashboard/src/context/TraceDataContext.tsx` | 383 |
| `addFlag` | Function | `dashboard/src/context/FlagContext.tsx` | 22 |
| `removeFlag` | Function | `dashboard/src/context/FlagContext.tsx` | 38 |
| `resolveFlag` | Function | `dashboard/src/context/FlagContext.tsx` | 46 |
| `unresolveFlag` | Function | `dashboard/src/context/FlagContext.tsx` | 54 |
| `appendRecord` | Function | `dashboard/src/context/TraceDataContext.tsx` | 190 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `App → HasTraceIdentity` | cross_community | 6 |
| `App → LatestTimestamp` | cross_community | 4 |
| `App → BuildRecordKeySet` | cross_community | 4 |
| `App → CountBoolMapDiffs` | cross_community | 4 |
| `Dashboard → UseTraceDataSource` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Data | 1 calls |
| Ui | 1 calls |

## How to Explore

1. `context({name: "classifyLine"})` — see callers and callees
2. `query({search_query: "context"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
