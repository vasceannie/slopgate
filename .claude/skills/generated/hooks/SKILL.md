---
name: hooks
description: "Skill for the Hooks area of slopgate. 74 symbols across 3 files."
---

# Hooks

74 symbols | 3 files | Cohesion: 82%

## When to Use

- Working with code in `dashboard/`
- Understanding how buildTraceSessionIndexes, sessionIndexes, summarizeTopRules work
- Modifying hooks-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `dashboard/src/hooks/useTraceData.ts` | sessionBucket, repoLabelForPath, sessionRecords, firstString, nativeSessionIds (+56) |
| `dashboard/src/hooks/use-toast.ts` | genId, addToRemoveQueue, timeout, reducer, dispatch (+4) |
| `dashboard/src/hooks/useTraceData.test.ts` | finding, rules, event, events |

## Entry Points

Start here when exploring this area:

- **`buildTraceSessionIndexes`** (Function) — `dashboard/src/hooks/useTraceData.ts:730`
- **`sessionIndexes`** (Function) — `dashboard/src/hooks/useTraceData.ts:1025`
- **`summarizeTopRules`** (Function) — `dashboard/src/hooks/useTraceData.ts:133`
- **`useTraceData`** (Function) — `dashboard/src/hooks/useTraceData.ts:831`
- **`reducer`** (Function) — `dashboard/src/hooks/use-toast.ts:70`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `buildTraceSessionIndexes` | Function | `dashboard/src/hooks/useTraceData.ts` | 730 |
| `sessionIndexes` | Function | `dashboard/src/hooks/useTraceData.ts` | 1025 |
| `summarizeTopRules` | Function | `dashboard/src/hooks/useTraceData.ts` | 133 |
| `useTraceData` | Function | `dashboard/src/hooks/useTraceData.ts` | 831 |
| `reducer` | Function | `dashboard/src/hooks/use-toast.ts` | 70 |
| `resolveDecision` | Function | `dashboard/src/hooks/useTraceData.ts` | 60 |
| `operationalContext` | Function | `dashboard/src/hooks/useTraceData.ts` | 1090 |
| `streamSchemaValidationWarning` | Function | `dashboard/src/hooks/useTraceData.ts` | 80 |
| `sourceStatus` | Function | `dashboard/src/hooks/useTraceData.ts` | 1139 |
| `windowMs` | Function | `dashboard/src/hooks/useTraceData.ts` | 834 |
| `sessionBucket` | Function | `dashboard/src/hooks/useTraceData.ts` | 218 |
| `repoLabelForPath` | Function | `dashboard/src/hooks/useTraceData.ts` | 242 |
| `sessionRecords` | Function | `dashboard/src/hooks/useTraceData.ts` | 256 |
| `firstString` | Function | `dashboard/src/hooks/useTraceData.ts` | 260 |
| `nativeSessionIds` | Function | `dashboard/src/hooks/useTraceData.ts` | 286 |
| `firstPlatform` | Function | `dashboard/src/hooks/useTraceData.ts` | 299 |
| `firstPlatformSource` | Function | `dashboard/src/hooks/useTraceData.ts` | 308 |
| `firstLineageRole` | Function | `dashboard/src/hooks/useTraceData.ts` | 317 |
| `lineageConfidenceFor` | Function | `dashboard/src/hooks/useTraceData.ts` | 326 |
| `deriveLineageRole` | Function | `dashboard/src/hooks/useTraceData.ts` | 338 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Dashboard → IsSelfTestSessionId` | cross_community | 4 |
| `Dashboard → UseTraceDataSource` | cross_community | 3 |
| `Dashboard → FilterByTime` | cross_community | 3 |
| `Dashboard → FilterByPlatform` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Context | 1 calls |

## How to Explore

1. `context({name: "buildTraceSessionIndexes"})` — see callers and callees
2. `query({search_query: "hooks"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
