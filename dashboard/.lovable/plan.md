

# Slopgate Flight Recorder Dashboard

A dark, terminal-aesthetic dashboard that visualizes slopgate's JSONL trace data across six panels — a richer, live version of `slopgate stats`.

## Data Layer

Generate realistic mock data matching the exact trace schema from `TraceWriter`:
- **events.jsonl** shape: `{timestamp, platform, event_name, session_id, tool_name, candidate_paths, languages}`
- **rules.jsonl** shape: `{timestamp, platform, event_name, session_id, tool_name, rule_id, severity, decision, message, additional_context, metadata}`
- **results.jsonl** shape: `{timestamp, platform, event_name, session_id, tool_name, findings[], errors[], output, skipped?, reason?}`
- **subprocess.jsonl** shape: `{timestamp, event_name, session_id, command, cwd, returncode, stdout, stderr}`

Mock data will span ~7 days across all five platforms (Claude, Codex, OpenCode, Cursor, Pi), covering all event types (SessionStart, PreToolUse, PermissionRequest, PostToolUse, PostToolUseFailure, Stop), all decision types (allow, deny, block, ask, context, warn), and a realistic distribution of the ~69 rules (30 Python + 39 regex). Include async job traces with mixed pass/fail.

## Layout & Design

- **Theme**: Dark background (`#0a0e17`), monospace font (JetBrains Mono/Fira Code via Google Fonts), green/amber/red signal colors. Terminal-inspired card borders with subtle glow on active elements.
- **Color system**: `allow` → muted green, `deny/block` → red, `ask` → amber, `context/warn` → blue, `error` → magenta.
- **Top bar**: Time window selector (1h, 6h, 24h, 7d, 30d) + platform filter chips (Claude / Codex / OpenCode / Cursor / Pi / All).

## Six Panels

### 1. Guardrail Posture Strip (top row, narrow)
KPI cards in a horizontal strip:
- Total hook invocations
- Block rate (%)
- Deny rate (%)
- Ask rate (%)
- Allow-with-rewrite count
- Skipped repo/path count
- Rule engine error count

Each card shows value + sparkline trend for the selected window. Red/green delta indicator vs previous period.

### 2. Decision Funnel (second row, left)
Stacked area time series showing event volume over time, colored by decision outcome (allow/deny/block/ask/warn/context). 

Below it, a funnel visualization: SessionStart → PreToolUse → PermissionRequest → PostToolUse → Stop, with counts at each stage and drop-off percentages. Platform breakdown on hover via tooltip.

Built with **@nivo/line** (stacked area) and **@nivo/funnel**.

### 3. Top Pressure Rules (second row, right)
Horizontal bar chart of top 15 firing rules, colored by severity (LOW/MEDIUM/HIGH/CRITICAL). Toggleable between "top firing," "top blocking," and "top warning-only."

A sub-section groups duplication-family findings (repeated-code-block, duplicate-call-sequence, semantic-clone) as a distinct lens with their own trend sparklines.

Severity mix donut chart in the corner.

Built with **@nivo/bar** and **@nivo/pie**.

### 4. Session & Tool Explorer (third row, full width)
Sortable/filterable table:
- Session ID (truncated, copyable)
- Platform badge
- Event count sparkline
- Tools touched (chips)
- Languages detected
- Candidate paths count
- Final outcome (allow/deny/block badge)
- Duration

Clicking a row expands an inline timeline showing the exact sequence: hook event → evaluated rules → winning decision → adapter output → optional async jobs. Each node is color-coded by decision. Rule findings show rule_id, severity, message snippet.

### 5. Async Jobs / Quality Follow-up (bottom row, left)
- Pass/fail rate donut by command
- Median runtime bar chart
- "Noisy commands" list (highest failure rate)
- Failure output snippets (expandable, monospace)

Data sourced from subprocess trace records.

Built with **@nivo/pie** and **@nivo/bar**.

### 6. Drift & Tuning (bottom row, right)
- Disabled rules list with last-disabled date
- Active severity overrides (rule → override level)
- Skipped repos list
- Hottest repos (most hook invocations)
- Block rate trend per rule (sparkline) to detect if a config change shifted behavior

Config values pulled from the mock `RuntimeConfig` shape (disabled_rules, severity_overrides, skip_paths).

## Pages & Navigation

Single-page dashboard with a minimal sidebar:
- **Dashboard** (main view with all 6 panels)
- **Session Detail** (expanded timeline view when clicking a session row — could be a slide-over drawer)

## Dependencies to Add

- `@nivo/core`, `@nivo/line`, `@nivo/bar`, `@nivo/pie`, `@nivo/funnel` — charting
- No backend needed; all mock data generated client-side

## File Structure

- `src/data/mockTraces.ts` — mock data generators matching slopgate's JSONL schemas
- `src/types/slopgate.ts` — TypeScript types for HookEvent, RuleFinding, HookResult, SubprocessRun
- `src/pages/Dashboard.tsx` — main dashboard layout
- `src/components/dashboard/PostureStrip.tsx` — Panel 1
- `src/components/dashboard/DecisionFunnel.tsx` — Panel 2
- `src/components/dashboard/TopRules.tsx` — Panel 3
- `src/components/dashboard/SessionExplorer.tsx` — Panel 4
- `src/components/dashboard/AsyncJobs.tsx` — Panel 5
- `src/components/dashboard/DriftTuning.tsx` — Panel 6
- `src/components/dashboard/SessionTimeline.tsx` — Expandable session detail
- `src/components/dashboard/TimeWindowSelector.tsx` — Shared time/platform filter controls
- `src/hooks/useTraceData.ts` — Data filtering/aggregation logic

