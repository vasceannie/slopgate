---
name: gitnexus-area-hooks
description: "Skill for the Hooks area of slopgate. 80 symbols across 6 files."
---

# Hooks

80 symbols | 6 files | Cohesion: 83%

## When to Use

- Working with code in `dashboard/`
- Understanding how buildTraceSessionIndexes, sessionIndexes, reducer work
- Modifying hooks-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `dashboard/src/hooks/useTraceData.ts` | buildTraceSessionIndexes, deriveLineageRole, firstLineageRole, firstPlatform, firstPlatformSource (+58) |
| `dashboard/src/hooks/use-toast.ts` | addToRemoveQueue, timeout, dispatch, genId, reducer (+5) |
| `dashboard/src/hooks/useTraceData.test.ts` | event, events, finding, rules |
| `dashboard/src/lib/improvement.ts` | episodeScopeConfidenceCounts |
| `dashboard/src/lib/improvementScope.ts` | recordScopeConfidence |
| `dashboard/src/lib/sessionHelpers.ts` | SessionData |

## Entry Points

Start here when exploring this area:

- **`buildTraceSessionIndexes`** (Function) — `dashboard/src/hooks/useTraceData.ts:732`
- **`sessionIndexes`** (Function) — `dashboard/src/hooks/useTraceData.ts:1027`
- **`reducer`** (Function) — `dashboard/src/hooks/use-toast.ts:70`
- **`summarizeTopRules`** (Function) — `dashboard/src/hooks/useTraceData.ts:135`
- **`useTraceData`** (Function) — `dashboard/src/hooks/useTraceData.ts:833`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `buildTraceSessionIndexes` | Function | `dashboard/src/hooks/useTraceData.ts` | 732 |
| `sessionIndexes` | Function | `dashboard/src/hooks/useTraceData.ts` | 1027 |
| `reducer` | Function | `dashboard/src/hooks/use-toast.ts` | 70 |
| `summarizeTopRules` | Function | `dashboard/src/hooks/useTraceData.ts` | 135 |
| `useTraceData` | Function | `dashboard/src/hooks/useTraceData.ts` | 833 |
| `resolveDecision` | Function | `dashboard/src/hooks/useTraceData.ts` | 62 |
| `operationalContext` | Function | `dashboard/src/hooks/useTraceData.ts` | 1092 |
| `episodeScopeConfidenceCounts` | Function | `dashboard/src/lib/improvement.ts` | 192 |
| `recordScopeConfidence` | Function | `dashboard/src/lib/improvementScope.ts` | 253 |
| `streamSchemaValidationWarning` | Function | `dashboard/src/hooks/useTraceData.ts` | 82 |
| `sourceStatus` | Function | `dashboard/src/hooks/useTraceData.ts` | 1147 |
| `windowMs` | Function | `dashboard/src/hooks/useTraceData.ts` | 836 |
| `SessionData` | Interface | `dashboard/src/lib/sessionHelpers.ts` | 19 |
| `deriveLineageRole` | Function | `dashboard/src/hooks/useTraceData.ts` | 340 |
| `firstLineageRole` | Function | `dashboard/src/hooks/useTraceData.ts` | 319 |
| `firstPlatform` | Function | `dashboard/src/hooks/useTraceData.ts` | 301 |
| `firstPlatformSource` | Function | `dashboard/src/hooks/useTraceData.ts` | 310 |
| `firstString` | Function | `dashboard/src/hooks/useTraceData.ts` | 262 |
| `lineageConfidenceFor` | Function | `dashboard/src/hooks/useTraceData.ts` | 328 |
| `nativeSessionIds` | Function | `dashboard/src/hooks/useTraceData.ts` | 288 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `OperationalContext → ClassifyFollowup` | cross_community | 4 |
| `OperationalContext → ProvenanceKey` | cross_community | 4 |
| `OperationalContext → CreateEpisode` | cross_community | 4 |
| `OperationalContext → TimestampSortKey` | cross_community | 4 |
| `OperationalContext → RoundTo` | cross_community | 4 |
| `Dashboard → IsSelfTestSessionId` | cross_community | 4 |
| `BuildTraceSessionIndexes → ResolveDecision` | cross_community | 3 |
| `OperationalContext → RecordScopeConfidence` | intra_community | 3 |
| `OperationalContext → StructuralScopeKeyForRule` | cross_community | 3 |
| `OperationalContext → EpisodeCounts` | cross_community | 3 |

## How to Explore

1. `context({name: "buildTraceSessionIndexes"})` — see callers and callees
2. `query({search_query: "hooks"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
