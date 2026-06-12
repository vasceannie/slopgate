# Session and Tool Explorer Improvement Spec

Date: 2026-06-12
Status: Draft
Owner surface: `dashboard/src/components/dashboard/SessionExplorer.tsx` and `dashboard/src/components/dashboard/SessionTimeline.tsx`

## Design Context

This surface is an operator console for Slopgate trace replay. The primary users are developers and maintainers investigating hook decisions across Claude, Codex, OpenCode, and related harnesses. They are usually trying to answer four questions quickly:

- What happened in this session?
- Which hook/tool/rule made the important decision?
- What exact payload, path, command, or diff caused it?
- What should I inspect or fix next?

The right tone is forensic, dense, and calm. It should keep the terminal-inspired identity, but it should not feel like an undifferentiated raw log dump. The current dark theme and compact table are appropriate for long debugging sessions; the improvement should sharpen hierarchy and operator confidence without turning the dashboard into a marketing surface.

## Evidence Reviewed

- Selected DOM element from the in-app preview at `http://airbox:18835/`.
- Existing screenshots: `dashboard-details-screenshot.png` and `dashboard-real-result-drilldown.png`.
- `dashboard/src/components/dashboard/SessionExplorer.tsx`, especially the session table, filter row, clickable session rows, and expanded timeline mount.
- `dashboard/src/components/dashboard/SessionTimeline.tsx`, especially timeline filters, `auditRows`, row rendering, expanded detail payload panels, and missing tool input states.
- `dashboard/src/index.css`, `dashboard/tailwind.config.ts`, and `dashboard/src/lib/chartTheme.ts` for current color, typography, and signal tokens.
- Deterministic design scan: `npx impeccable --json dashboard/src` returned `[]`.

## Critique Summary

The table is useful and domain-shaped, but the information hierarchy is backwards. It exposes raw event metadata, compact chips, and timeline mechanics before it answers the operator's main question: "What mattered in this session?"

The UI is not failing because of generic AI-design anti-patterns. The deterministic scan found no markup-pattern issues. The main design debt is operational UX: too much equally weighted trace material, weak session-to-decision storytelling, tiny text, and controls that are visually present but not self-explanatory.

## Design Health Score

| # | Heuristic | Score | Key issue |
|---|---|---:|---|
| 1 | Visibility of system status | 3 | Decisions, findings, errors, and live status are visible, but the important session cause is not promoted. |
| 2 | Match system / real world | 2 | Labels like `PostToolUse`, `session lifecycle`, and `Focus on Agent Behavior` assume internal Slopgate knowledge. |
| 3 | User control and freedom | 2 | Filtering and paging exist, but expanded context resets often and the table row itself is the main expansion control. |
| 4 | Consistency and standards | 3 | Badges and filter chips are consistent; the same filter/menu primitive is duplicated between table and timeline. |
| 5 | Error prevention | 2 | Low-risk viewer, but ambiguous filters and raw trace labels make misreading likely. |
| 6 | Recognition rather than recall | 2 | Users must remember what each hook event means and infer event/result pairing from compact rows. |
| 7 | Flexibility and efficiency | 2 | Power users get pagination and filters, but no session search, row comparison, keyboard-first path, or direct "show cause" path. |
| 8 | Aesthetic and minimalist design | 2 | The density is appropriate, but most elements share similar visual weight and the expanded detail reads as a wall of trace facts. |
| 9 | Error recovery | 2 | Missing drilldown and missing tool input states exist, but they do not help users recover or understand trace vintage/correlation limits deeply. |
| 10 | Help and documentation | 1 | There is no contextual explanation for hook names, decisions, correlation, or missing payloads. |
| Total |  | 21/40 | Acceptable foundation; significant UX improvements needed before the view feels operator-grade. |

## Cognitive Load

Failed checklist count: 5 of 8, high load.

- Single focus: failed. The user is asked to process the session table, expanded row, timeline, filters, flag control, and detail payload at once.
- Chunking: failed. `auditRows` emits nine values into a two-column grid without a stronger primary/secondary split.
- Grouping: partial pass. Related payload panels are grouped, but trace facts, evidence, and metadata are mixed.
- Visual hierarchy: failed. A harmless allow row and a high-value failure row can look nearly equal beyond color.
- One thing at a time: failed. Expansion immediately reveals timeline navigation, metadata, findings, model, command, input, output, and warnings.
- Minimal choices: partial fail. Filter menus can expose many events/tools; "Details" labels are ambiguous.
- Working memory: failed. Users must remember the selected session row while reading an inner scroll region.
- Progressive disclosure: partial pass. Rows expand and payloads have pretty/raw modes, but the first expanded view still exposes too much.

## Persona Red Flags

Alex, power user:

- Cannot search within sessions by rule, path, command, or tool payload.
- Can only expand one session row and one timeline row at a time, making comparison awkward.
- No visible keyboard accelerators for next/previous event, expand/collapse, copy row ID, or jump to first blocking finding.

Sam, accessibility-dependent user:

- Session rows are clickable `<tr>` elements, not a dedicated keyboard-first row expander.
- Many controls and values use 10px text, which is too small for a dense operational console.
- Several icon-only controls rely on visual recognition; flag/copy controls need consistently discoverable labels and visible focus treatment.

Jordan, first-time investigator:

- Hook names are not translated into operational language.
- "Focus on Agent Behavior (Hide Noise)" is long and vague; it does not say what will remain visible.
- The expanded detail starts with metadata instead of a plain verdict summary.

Riley, stress tester:

- Long paths and payloads are mostly handled with truncation and scroll containers, but the user cannot easily tell when hidden data is the important data.
- Missing tool body copy explains trace capture history, but there is no recovery action such as "show correlated event" or "filter to nearby records."
- Event/result correlation is implicit; if the pairing is wrong or absent, the UI does not expose the confidence of the match.

## Priority Issues

### P1: The expanded view does not answer "what mattered" first

Current behavior: expanded timeline rows begin with `auditRows`, then optional files/context/findings/payloads. The operator sees session ID, platform, event name, tool, times, decision, findings, and errors before seeing the reason this row matters.

Why it matters: a user investigating a block or denial has to translate trace metadata into a causal story. That slows diagnosis and increases the chance of reading the wrong row.

Fix: add a session outcome summary and a timeline row verdict summary before trace metadata.

### P1: The table and timeline fight for context

Current behavior: the session table expands into a fixed `h-[520px]` inner scroller. At the selected viewport, the user can see only part of the inner timeline, while the parent row context remains above or outside the scroll focus.

Why it matters: the operator has to keep the outer session row in memory while scrolling the nested timeline. This is especially painful when multiple sessions have similar IDs and tools.

Fix: convert the expanded row into a detail bay with a sticky session summary, a compact timeline list, and a stable selected-event detail pane.

### P1: Hook/result pairing is present but not visually decisive

Current behavior: `SessionTimeline` can create composite `hook` rows that pair an event with a result, but the visual design still treats the row like one more log item.

Why it matters: the pairing is the core Slopgate concept. Operators need to see "tool intent -> hook evaluation -> decision -> evidence" as one unit.

Fix: make composite hook rows the primary timeline unit and visually separate lifecycle noise, subprocesses, standalone findings, and unmatched raw events.

### P2: Filtering language is ambiguous

Current behavior: nested filters use `Event`, `Tool`, `Decision`, and `Details`, with `Findings` and `Errors` as detail toggles. "Focus on Agent Behavior (Hide Noise)" is a checkbox.

Why it matters: users cannot predict exactly what the controls will hide. Ambiguous filters are risky in a trace/debugging tool because they can hide the causal record.

Fix: rename filters around predicates and show active filter summaries. Use "Has findings" and "Has errors"; rename the checkbox to "Agent actions only"; add a one-click "Clear timeline filters."

### P2: Accessibility and keyboard interaction lag behind the visual design

Current behavior: session expansion is driven by row click, timeline rows are buttons, and many labels are 10px.

Why it matters: this is a debugging tool where users may spend long sessions scanning dense text. Small text and pointer-first row controls hurt precision and accessibility.

Fix: add explicit expand buttons, larger detail text, clear focus states, and keyboard shortcuts that do not conflict with browser defaults.

## Proposed UX Direction

The improved view should feel like a flight recorder, not a spreadsheet with logs inside it. Keep the dark operational aesthetic, but reshape the hierarchy:

- Session table: scan many sessions quickly.
- Expanded session bay: summarize one session's outcome and causal path.
- Timeline lane: navigate events and hook decisions.
- Detail pane: inspect evidence for the selected event.
- Raw trace: available, but never the first thing users must parse.

## Information Architecture

### Session Table

Keep the table, but make columns more diagnostic.

Recommended columns:

- Expander
- Session
- Outcome
- Primary cause
- Platform
- Agent activity
- Files / paths
- Duration
- Actions

Column behavior:

- `Primary cause` should show the highest-severity blocking or denying rule when present. If the session allowed cleanly, show `Clean allow`. If the session has warnings/context only, show the strongest advisory rule.
- `Agent activity` should show the last meaningful agent tool and a `+N` count, rather than only the first four tools.
- `Files / paths` should prefer paths associated with the primary cause before generic candidate paths.
- `Events` can move into a secondary metadata line or tooltip; it is rarely the first diagnostic answer.

### Expanded Session Bay

Replace the full-width raw nested scroller with a two-zone detail bay.

Left zone: timeline navigator.

- Default selection should be the first blocking/denying row, then first row with findings, then newest composite hook row.
- Show composite hook rows as the default primary row type:
  - Agent action: event + tool + path/command summary.
  - Hook decision: allow/deny/block/ask/context.
  - Evidence: rule count, error count, primary rule.
- De-emphasize lifecycle-only allow rows unless they have findings/errors.
- Keep raw standalone events accessible under an "Unmatched trace events" group.

Right zone: selected event detail.

- Sticky within the expanded bay.
- Starts with a verdict strip:
  - Decision
  - Why
  - Tool / lifecycle source
  - File/path/command summary
  - Findings/errors
- Then evidence sections:
  - Focused diff or command
  - Tool input
  - Hook output
  - Grouped findings
  - Trace metadata
- Raw JSON remains behind the existing pretty/raw segmented controls.

### Trace Metadata

Split `auditRows` into two groups.

Primary facts:

- Event
- Tool
- Decision
- Primary rule / finding count

Trace metadata:

- Session ID
- Platform
- Event time
- Result time
- Error count
- Correlation status

The trace metadata group should be collapsed by default when a row has meaningful evidence. It can be open by default only when the row has no payload, no findings, and no command/diff.

### Filters and Search

Add a session-level search box above the table.

Search should match:

- Session ID
- Platform
- Outcome
- Tool name
- Rule ID
- Candidate path basename and full path
- Command text

Timeline filters:

- Rename `Details` to `Rows`.
- Rename `Findings` to `Has findings`.
- Rename `Errors` to `Has errors`.
- Rename `Focus on Agent Behavior (Hide Noise)` to `Agent actions only`.
- Show a compact active filter summary: `Event: PostToolUse | Tool: TodoWrite | Has findings`.
- Add `Clear timeline filters`.

Do not hide blocked/denied rows when `Agent actions only` is enabled.

### Visual Treatment

Keep the dashboard dark and dense, but adjust hierarchy.

- Increase detail text from 10px to at least 11px, preferably 12px for payload labels and verdict summaries.
- Use signal color primarily for decisions and severity, not every piece of metadata.
- Replace the single small timeline dot as the only status signifier with a small icon plus color for decision states:
  - allow: shield/check style
  - deny/block: stop/ban style
  - ask/warn/context: alert/info style
- Use tinted full-row backgrounds sparingly for active/selected rows.
- Keep cards out of cards. The expanded bay should be an unframed table extension with internal panes and separators, not nested card stacks.
- Preserve monospaced payloads, but use a non-mono or less mechanical label style for UI labels if the current design system allows it.

### Accessibility

- Make the session expander an actual button in the first cell with `aria-expanded`, `aria-controls`, and a useful label.
- Do not rely on `<tr onClick>` as the only expansion mechanism.
- Keep row click as a convenience only if keyboard and screen-reader paths are first-class.
- Ensure copy and flag icon buttons have visible focus states and accessible names.
- Ensure all popover menus close on Escape and return focus to the trigger.
- Maintain readable text at 200% zoom without horizontal overlap.
- Ensure selected timeline row state is announced through `aria-current` or `aria-selected`.

## Data Derivations

Add small pure helper functions before UI restructuring. These can be unit-tested without rendering:

- `primarySessionCause(session)`: returns primary decision, primary rule, severity, message, event name, tool name, and path.
- `sessionActivitySummary(session)`: returns last meaningful tool, tool count, event count, path summary.
- `initialTimelineSelection(entries)`: chooses the best default timeline row.
- `timelineRowSummary(entry)`: returns title, subtitle, decision label, and primary evidence label.
- `correlationStatus(entry)`: returns `matched`, `nearby`, `unmatched`, or `historical-missing-input`.

These helpers should prefer existing trace types and selectors. They should not introduce new API requirements.

## Component Plan

Phase 1: hierarchy and semantics.

- Add helper functions for primary cause, row summaries, and initial timeline selection.
- Add a `SessionOutcomeSummary` component rendered immediately inside the expanded row.
- Add a `TimelineVerdictStrip` component at the top of expanded timeline detail.
- Split `auditRows` into primary facts and collapsed trace metadata.
- Add tests for primary cause selection and default timeline selection.

Phase 2: layout.

- Replace the fixed single-column expanded timeline with a responsive detail bay.
- Desktop: two columns, timeline list on the left and sticky detail pane on the right.
- Narrow widths: timeline list above detail pane, with the selected detail immediately following the selected row.
- Preserve current payload panels and pretty/raw behavior.
- Add screenshot verification at `1399x1266` and a narrow mobile viewport.

Phase 3: filters and search.

- Add session search.
- Rename timeline filters.
- Add active filter summary and clear action.
- Ensure `Agent actions only` preserves blocks, denies, errors, and findings.

Phase 4: accessibility and polish.

- Replace row-click-only expansion with explicit expander button semantics.
- Add Escape/focus return for filter menus.
- Increase small text sizes where density permits.
- Add tooltips for icon-only flag/copy controls if not already present.

## Acceptance Criteria

- At `1399x1266`, expanding the selected session shows final outcome, primary cause, tool/lifecycle source, file/path/command summary, and findings/errors without scrolling the inner timeline.
- A blocking or denying session defaults to the most relevant blocking/denying timeline row, not merely the newest lifecycle row.
- A clean allow session still communicates that it is clean and does not look like an unresolved mystery.
- The operator can search sessions by session ID, rule ID, tool name, path, and command text.
- Timeline filters clearly show what is active and can be cleared in one action.
- Missing tool input states distinguish historical trace limitations from current correlation failures.
- Keyboard-only users can expand sessions, move through timeline rows, open/close filter menus, switch pretty/raw payload views, copy session IDs, and flag entries.
- At 200% browser zoom, session IDs, paths, badges, and payload labels do not overlap.
- The deterministic scanner remains clean: `npx impeccable --json dashboard/src` returns no new findings.

## Test Plan

Unit and component tests:

- `SessionExplorer` renders a primary cause for block/deny sessions with findings.
- `SessionExplorer` renders `Clean allow` for sessions with allow outcome and zero findings/errors.
- Session expansion uses an accessible button with `aria-expanded`.
- Session search matches session ID, tool, rule ID, path basename, full path, and command text.
- `SessionTimeline` default selection prefers block/deny, then findings, then newest composite row.
- `Agent actions only` still keeps deny/block/error/finding rows visible.
- Missing historical tool input renders the historical capture explanation.
- Pretty/raw toggles remain available for command, diff, tool input, and output panels.

Manual verification:

```bash
npm --prefix dashboard run test -- SessionExplorer SessionTimeline
npm --prefix dashboard run lint
npx impeccable --json dashboard/src
make dashboard-dev
```

Visual checks:

- Desktop: `http://airbox:18835/`, `1399x1266`.
- Narrow viewport: 390px wide.
- Confirm expanded details are readable, no text overlaps, and the selected event detail remains tied to the selected timeline row.

## Non-Goals

- No dashboard-wide rewrite.
- No trace schema migration.
- No new backend API required for phase 1.
- No visual theme overhaul beyond local hierarchy, text-size, and signal refinements.
- No replacement of the existing pretty/raw payload inspection model.

## Open Questions

- Should default timeline order remain newest-first, or should expanded sessions default to story order with a newest-first toggle?
- Should multiple timeline rows be expandable at once for comparison, or should the new detail pane remain single-selection?
- Should lifecycle events be hidden by default in clean sessions, or only when there is a non-lifecycle row with findings/errors?
- Should the session table expose a saved filter preset for common investigations, such as `Blocks`, `PostToolUse`, or `Quality lint`?
