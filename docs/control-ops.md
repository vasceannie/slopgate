# Rules Operations Console Plan

## Summary

Rebuild the selected Rules tab into a focused configuration, administration, and monitoring layer for rule surfaces, scoped to the Rules tab only. Keep the current forensic, dense, dark "flight recorder" identity, but replace the raw 10-column rule matrix with an operator workflow centered on configuring hook/CLI surfaces, actions, events, exclusions, and save review.

The current design critique is: acceptable foundation, not operator-grade. The UI exposes useful primitives, but it overloads users with columns, tiny mono-heavy text, mixed monitoring/config controls, and weak workflow hierarchy. The deterministic `impeccable` scan returned `[]`, so the issue is not obvious AI-slop markup; it is information architecture, typography, and layout.

## Key Changes

- Split `dashboard/src/components/dashboard/RuleManager.tsx` (~1300 lines) into a small facade plus a `rules/` subpackage for derived data, layout sections, row rendering, inspector panels, and tests. Preserve the exported `RuleManager` component so `Dashboard.tsx` does not need a routing change.
- Keep existing config contracts for v1: `enabled_rules`, `enabled_cli_rules`, `rule_surfaces`, `rule_counterparts`, `regex_rules`, and `skip_paths`. Do not change `src/slopgate/models.py` or `RuleSurfaceConfig`; GitNexus marked that model as CRITICAL blast radius.
- Redesign the Rules tab as a three-zone operations console:
  - Top command/status band: API status, pending changes, save/discard actions, global `skip_paths`, and compact totals for hook on/off, CLI on/off, disabled, and recently firing rules.
  - Main rules workbench: category/filter navigation plus a denser but clearer rule list with stable columns for rule identity, effective surface state, action, severity, recent fires, and configuration status.
  - Rule inspector: selected rule details, hook/CLI controls, event selector, action selector, exclusion editor, counterpart mapping, unsupported-surface reason, and "effective behavior" summary.
- Make "Configure surfaces" the primary workflow:
  - Selecting a rule opens the inspector instead of expanding inline rows.
  - Hook and CLI enablement are grouped together with labels and unsupported reasons.
  - Hook action and event filters are edited in the inspector, not buried inside a row expansion.
  - Regex path exclusions and global `skip_paths` are visually separated so operators understand rule-specific versus global suppression.
- Improve monitoring without making it the primary path:
  - Keep recent fire counts visible.
  - Add compact "hot", "disabled", "partial", and "unsupported" filters.
  - Show category summaries as operational status, not decorative metric cards.
- Improve typography and layout:
  - Move general UI copy to a readable sans stack and reserve mono for rule IDs, commands, paths, globs, and config keys.
  - Replace 9-10px body/control text with a fixed app scale: `0.75rem` captions, `0.875rem` metadata, `1rem` primary body/control text where space allows, with tighter density only for table metadata.
  - Use a 4pt spacing rhythm with tight related controls and larger separation between workflow zones.
  - Keep cards at existing small radii, avoid nested cards, and use dividers, bands, and inspector layout rather than card grids.
- Add an explicit pending-change review surface before save:
  - Show changed rule IDs and changed fields derived from the existing saved/current config comparison.
  - Keep the existing `POST /api/config` patch shape.
  - Preserve current timeout/error behavior and display save errors next to the command band.

## Public APIs / Interfaces

- No backend API schema change for v1.
- No change to `RuleSurfaceConfig`, `HookSurfaceConfig`, `CliSurfaceConfig`, or Python config merge semantics.
- Frontend-only internal additions are acceptable:
  - Derived UI model for `RuleOperationsRow`, `RuleCategorySummary`, and pending-change entries.
  - Internal helper functions for effective surface state, unsupported reason labels, category summaries, and config diff generation.
- Existing user-facing behavior must remain:
  - `/api/config` health/read/write path still drives live config.
  - Static/baked config still works read-only when the API is unavailable.
  - `RuleManager` still accepts `fireCounts: Map<string, number>`.

## Test Plan

- Run GitNexus impact before implementation on each edited symbol. Current planning checks found:
  - `RuleManager`: LOW risk, direct test caller only.
  - `RulesConfigProvider`: MEDIUM risk, affects entire app tree via `App.tsx`.
  - `apply_config_patch`: LOW risk, called by ForceDash config update path.
  - `RuleSurfaceConfig`: CRITICAL risk, avoid changing it for this work.
- Add/extend React tests in `dashboard/src/components/dashboard/RuleManager.test.tsx` or a colocated rules test suite:
  - Selecting a rule opens inspector controls for hook enablement, CLI enablement, action, events, exclusions, counterparts, and unsupported reasons.
  - Hook and CLI toggles still call `setRuleHookSurface` / `setRuleCliSurface` with the same payloads as today.
  - CLI counterpart rows remain folded into canonical hook rows.
  - CLI-only and hook-only rows show explicit unsupported reason labels.
  - Pending-change review lists changed rules/fields and save/discard states.
  - Global `skip_paths` remains editable and distinct from regex `exclude_path_globs`.
  - "changed" filter correctly identifies rules with pending modifications.
- Keep existing backend tests passing:
  - `rtk pytest tests/dashboard/test_forcedash_config_api.py`
  - `rtk pytest tests/engine/test_rule_surfaces.py`
- Run frontend verification:
  - `rtk npm --prefix dashboard run test -- RuleManager`
  - `rtk npm --prefix dashboard run lint`
  - `rtk npx impeccable --json dashboard/src/components/dashboard dashboard/src/pages dashboard/src/context dashboard/src/App.tsx`
- Run repo quality before finishing:
  - `rtk uv run slopgate lint check`
  - If scope touches shared Python config/API code, also run the focused Python tests above and the project quality command.

## Assumptions

- Scope is the Rules layer only, not a dashboard-wide IA rewrite.
- Primary workflow is configuring rule surfaces: hook/CLI placement, action, events, exclusions, and save review.
- Visual tone stays forensic, dense, and calm; this should feel like an operator console, not a marketing page or generic enterprise admin skin.
- Existing `rule_surfaces` primitives are enough for v1; comprehensive means a better admin surface over current capabilities, not a new policy schema.
- Avoid modifying broad runtime model types unless a later requirement proves the existing config shape cannot represent the needed behavior.
- Shared extraction is allowed only when it removes real duplication or creates a stable domain boundary.

# Rules Operations Console Plan, Adversarial Reuse Pass

## Summary

Rework only the Rules tab into a comprehensive configuration, administration, and monitoring layer for rule surfaces. The primary workflow is configuring hook/CLI placement, hook action, hook events, exclusions, and save review. Keep the current forensic, dense, dark operator-console tone.

Adversarial review changed the plan in two important ways:

- Extend existing config and dashboard code first. Do not invent a new rule schema, a second config context, a new API route, or a separate UI kit.
- Split `RuleManager.tsx` only to create real ownership boundaries. Avoid pass-through wrappers and generic "shared" helpers unless two existing surfaces actually reuse the behavior.

## Existing Code To Reuse

- Reuse `RulesConfigContext` / `useRulesConfig` as the only rule-config state owner. Keep its current read, pending-count, save, discard, API availability, and read-only fallback semantics.
- Reuse existing frontend config types in `dashboard/src/types/slopgate.ts`: `SlopgateConfig`, `RuleMetadata`, `RuleHookSurface`, `RuleCliSurface`, `RuleSurfaceConfig`, `RuleSurfaceAction`, `RuleUiAction`.
- Reuse existing rule derivation behavior from `RuleManager.tsx`: CLI counterpart folding, unsupported-surface reasons, category grouping, regex exclusion editing, `skip_paths`, hook event filtering, and action overrides.
- Reuse `chartTheme.ts` for decision, severity, platform, and badge colors. Add any missing rule-surface styles there only if they are used by more than the Rules tab.
- Reuse shadcn/Radix primitives already present:
  - `Input`, `Switch`, `Select`, `Tabs`, `ToggleGroup`, `Button`, `Badge`, `Table`.
  - Use `Sheet` (already in `dashboard/src/components/ui/sheet.tsx`) only for mobile/narrow inspector fallback. On desktop, use a persistent inspector panel, not a modal/sheet.
- Reuse local dashboard UI patterns:
  - `FlaggedItemsPanel` segmented status toggle pattern (Active/Resolved) for rule status filters (active/disabled/partial/hot/changed).
  - `DriftTuning` `CountList` compact row pattern for category monitoring summaries.
  - `PathExplorer` dense tree/list rendering approach if long rule groups need progressive reveal.

## Implementation Changes

- Keep `dashboard/src/components/dashboard/RuleManager.tsx` as the compatibility import surface used by `Dashboard.tsx`, but turn it into a small facade only if needed. A facade is allowed because it preserves the existing public import boundary.
- Move owned rule UI internals into a cohesive subpackage, for example `dashboard/src/components/dashboard/rules/`, not a cluster of flat `_rule_*` siblings. Suggested ownership:
  - `model.ts`: rule derivation, summaries, pending-change diff, filter predicates.
  - `RuleWorkbench.tsx`: main Rules tab composition.
  - `RuleList.tsx`: category list/table, row selection, compact surface state.
  - `RuleInspector.tsx`: selected rule config controls.
  - `RuleCommandBand.tsx`: API/save/discard/pending/global skip-path controls.
- Extract reusable filter controls only if both `FlaggedItemsPanel` and the new Rules workbench consume them. If implementation would require broad churn in `FlaggedItemsPanel`, keep the rule filter controls local for this pass and record the duplication as future cleanup.
- Keep the current config contract unchanged:
  - `rule_surfaces[rule_id].hook.enabled`
  - `rule_surfaces[rule_id].hook.action`
  - `rule_surfaces[rule_id].hook.events`
  - `rule_surfaces[rule_id].cli.enabled`
  - `enabled_cli_rules`
  - `regex_rules[].exclude_path_globs`
  - `skip_paths`
- Do not edit `src/slopgate/models.py` or Python `RuleSurfaceConfig` for this UI pass. GitNexus impact marked that class CRITICAL because it fans out through the runtime engine, adapters, rules, config loader, and lint paths.
- Preserve existing backend behavior in `dashboard/scripts/forcedash_server/config_api.py`. Only touch it if the UI exposes a bug in current patching; otherwise the frontend should submit the same patch shape as today.
- Replace the current 10-column matrix with a three-zone console:
  - Command band: API/read-only state, pending changes, save/discard, global skip paths, and compact counts.
  - Workbench list: searchable/filterable rule rows grouped by category, with rule ID, title, effective surfaces, severity, action, fires, and changed status.
  - Inspector panel: selected rule details and controls for hook/CLI enablement, hook action, events, regex exclusions, counterparts, unsupported reasons, and effective behavior.
- Keep monitoring present but subordinate to configuration:
  - Show "hot", "disabled", "partial", "unsupported", and "changed" filters.
  - Show fire counts and category totals without turning the page into a chart dashboard.
  - Keep existing `fireCounts` input; do not add new trace aggregation for this pass.
- Typography/layout pass:
  - Use sans for normal labels and explanatory text; reserve mono for rule IDs, CLI collector IDs, paths, globs, config keys, commands, and JSON-like values.
  - Stop using 9-10px text for primary controls. Keep tiny text only for compact metadata where the control remains labeled and accessible.
  - Use a 4pt spacing rhythm, tighter inside control groups and wider between command band, list, and inspector.
  - Avoid nested cards. Use full-width bands, dividers, selected-row state, and a persistent inspector.

## Implementation Notes: New State Requirements

The following capabilities are not present in the current codebase and must be added:

1. **Per-rule "changed" status**: The current `RulesConfigContext` exposes only `pendingCount: number`. The new "changed" filter and the pending-change review surface require per-rule change detection. Options:
   - Add a `pendingChanges: Array<{rule_id: string; fields: string[]}>` derived value to `RulesConfigContext`, or
   - Compute it locally in `model.ts` by comparing `savedConfig` against `config` (requires passing both to the rules subpackage).
2. **Inspector selection state**: The current `RuleRow` uses inline `expanded` state. The inspector pattern requires a shared `selectedRuleId: string | null` state owned by `RuleWorkbench` or `RuleManager`.
3. **Mobile inspector fallback**: The `Sheet` component from `dashboard/src/components/ui/sheet.tsx` is available but unused in the Rules tab. Add a narrow-viewport detection (e.g., `useMediaQuery` or container query) to switch from persistent inspector to `Sheet`.

## Adversarial Risks To Guard Against

- Do not let "comprehensive" become schema creep. The first pass should be a better administration layer over current capabilities, not a new policy model.
- Do not duplicate the rule derivation logic while splitting files. Move the existing logic to the new owner and import it; do not reimplement parallel `buildRuleMetadata` variants.
- Do not create generic `DashboardCard`, `StatusBadge`, or `FilterThing` abstractions unless at least two current components use them immediately.
- Do not hide critical configuration behind a modal. The inspector should keep the selected rule and the rule list visible together on desktop.
- Do not make unsupported surfaces look disabled-but-editable. Unsupported must stay explicit: "command only", "config safety", "runtime payload", "session lifecycle", "source lint available", etc.
- Do not collapse hook and CLI state into one "enabled" control. The whole point of this layer is to make surface placement legible.
- Do not change runtime model classes or Python config parsing unless a failing test proves the current contract cannot support the UI.
- Do not use decorative metric cards as a substitute for workflow. Counts should answer operational questions: what is enabled, what changed, what is firing, what cannot run on a surface.

## Test Plan

- Before implementation, run GitNexus impact for every edited symbol. At minimum:
  - `RuleManager` in `dashboard/src/components/dashboard/RuleManager.tsx`
  - `RulesConfigProvider` if context behavior changes
  - Any moved helper that becomes a shared import
  - `apply_config_patch` only if backend patching changes
- Frontend tests:
  - `RuleManager` still renders from the existing `RuleManager` export.
  - Existing hook/CLI toggle tests continue to pass with unchanged callback payloads.
  - Selecting a rule opens the inspector and shows hook enablement, CLI enablement, action, events, exclusions, counterparts, unsupported reasons, and fire count.
  - Mapped CLI collectors remain folded into canonical hook rows.
  - CLI-only rows do not render hook switches and show "source lint available".
  - Hook-only rows do not render CLI switches and show the correct unsupported reason.
  - Regex rule exclusions update `setExclusions`; global skip paths update `setSkipPaths`.
  - Pending-change review lists changed rule IDs/fields and save/discard controls preserve current behavior.
  - Read-only API state disables save while keeping inspection/filtering available.
  - "changed" filter correctly identifies rules with pending modifications against saved config.
- Backend/regression tests:
  - `rtk pytest tests/dashboard/test_forcedash_config_api.py`
  - `rtk pytest tests/engine/test_rule_surfaces.py`
- Frontend verification:
  - `rtk npm --prefix dashboard run test -- RuleManager`
  - `rtk npm --prefix dashboard run lint`
  - `rtk npx impeccable --json dashboard/src/components/dashboard dashboard/src/pages dashboard/src/context dashboard/src/App.tsx`
- Final repo gate:
  - `rtk uv run slopgate lint check`
  - If any dashboard split triggers TypeScript or lint issues, fix source debt in touched files rather than suppressing it.

## Assumptions

- Scope remains the Rules layer only.
- Existing config primitives are sufficient for v1.
- The implementation should preserve the current `/api/config` contract and `RuleManager` import boundary.
- New code should mostly be moved or extended from current `RuleManager.tsx`, not rewritten from scratch.
- Shared extraction is allowed only when it removes real duplication or creates a stable domain boundary.
