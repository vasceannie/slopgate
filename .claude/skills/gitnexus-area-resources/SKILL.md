---
name: gitnexus-area-resources
description: "Skill for the Resources area of slopgate. 68 symbols across 2 files."
---

# Resources

68 symbols | 2 files | Cohesion: 84%

## When to Use

- Working with code in `src/`
- Understanding how event, logAdvisoryResult, nativeIdentityFields work
- Modifying resources-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `src/slopgate/resources/pi_extension.ts` | applyUpdatedInput, clearSlopgateContext, inputTransformFromUpdatedInput, isSlopgatePath, mergeToolResultPatch (+31) |
| `src/slopgate/resources/opencode_plugin.ts` | event, logAdvisoryResult, nativeIdentityFields, payloadForEvent, cloneArgs (+27) |

## Entry Points

Start here when exploring this area:

- **`event`** (Function) — `src/slopgate/resources/opencode_plugin.ts:844`
- **`logAdvisoryResult`** (Function) — `src/slopgate/resources/opencode_plugin.ts:667`
- **`nativeIdentityFields`** (Function) — `src/slopgate/resources/opencode_plugin.ts:633`
- **`payloadForEvent`** (Function) — `src/slopgate/resources/opencode_plugin.ts:650`
- **`slopgatePiExtension`** (Function) — `src/slopgate/resources/pi_extension.ts:675`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `event` | Function | `src/slopgate/resources/opencode_plugin.ts` | 844 |
| `logAdvisoryResult` | Function | `src/slopgate/resources/opencode_plugin.ts` | 667 |
| `nativeIdentityFields` | Function | `src/slopgate/resources/opencode_plugin.ts` | 633 |
| `payloadForEvent` | Function | `src/slopgate/resources/opencode_plugin.ts` | 650 |
| `slopgatePiExtension` | Function | `src/slopgate/resources/pi_extension.ts` | 675 |
| `execute` | Function | `src/slopgate/resources/opencode_plugin.ts` | 796 |
| `managedRepo` | Function | `src/slopgate/resources/opencode_plugin.ts` | 631 |
| `cloneArgs` | Function | `src/slopgate/resources/opencode_plugin.ts` | 214 |
| `eventIdentityFields` | Function | `src/slopgate/resources/opencode_plugin.ts` | 261 |
| `eventToolArgs` | Function | `src/slopgate/resources/opencode_plugin.ts` | 337 |
| `firstString` | Function | `src/slopgate/resources/opencode_plugin.ts` | 240 |
| `isAllowedWhileRepairRequired` | Function | `src/slopgate/resources/opencode_plugin.ts` | 592 |
| `isExplicitRepairCommand` | Function | `src/slopgate/resources/opencode_plugin.ts` | 578 |
| `isKnownEffectTool` | Function | `src/slopgate/resources/opencode_plugin.ts` | 604 |
| `mergeToolArgs` | Function | `src/slopgate/resources/opencode_plugin.ts` | 225 |
| `objectValue` | Function | `src/slopgate/resources/opencode_plugin.ts` | 250 |
| `outcomeFields` | Function | `src/slopgate/resources/opencode_plugin.ts` | 198 |
| `applyUpdatedInput` | Function | `src/slopgate/resources/pi_extension.ts` | 233 |
| `clearSlopgateContext` | Function | `src/slopgate/resources/pi_extension.ts` | 479 |
| `inputTransformFromUpdatedInput` | Function | `src/slopgate/resources/pi_extension.ts` | 333 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Execute → Spawn` | cross_community | 6 |
| `Execute → Finish` | cross_community | 5 |
| `Event → CloneArgs` | intra_community | 4 |
| `Execute → RepairTimeoutMs` | intra_community | 4 |
| `Event → FirstString` | intra_community | 3 |
| `Event → ObjectValue` | intra_community | 3 |
| `Event → Spawn` | cross_community | 3 |

## How to Explore

1. `context({name: "event"})` — see callers and callees
2. `query({search_query: "resources"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
