---
name: gitnexus-area-ui
description: "Skill for the Ui area of slopgate. 217 symbols across 56 files."
---

# Ui

217 symbols | 56 files | Cohesion: 86%

## When to Use

- Working with code in `dashboard/`
- Understanding how DriftTuning, FlagButton, FlaggedItemsPanel work
- Modifying ui-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `dashboard/src/components/ui/sidebar.tsx` | Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupAction (+22) |
| `dashboard/src/components/ui/menubar.tsx` | Menubar, MenubarCheckboxItem, MenubarContent, MenubarItem, MenubarLabel (+6) |
| `dashboard/src/components/ui/carousel.tsx` | Carousel, onSelect, CarouselContent, CarouselItem, CarouselNext (+5) |
| `dashboard/src/components/ui/context-menu.tsx` | ContextMenuCheckboxItem, ContextMenuContent, ContextMenuItem, ContextMenuLabel, ContextMenuRadioItem (+4) |
| `dashboard/src/components/ui/dropdown-menu.tsx` | DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuRadioItem (+4) |
| `dashboard/src/components/ui/alert-dialog.tsx` | AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter (+3) |
| `dashboard/src/components/ui/chart.tsx` | ChartContainer, ChartStyle, chartStyleContent, ChartLegendContent, ChartTooltipContent (+3) |
| `dashboard/src/components/ui/command.tsx` | Command, CommandDialog, CommandGroup, CommandInput, CommandItem (+3) |
| `dashboard/src/components/ui/table.tsx` | Table, TableBody, TableCaption, TableCell, TableFooter (+3) |
| `dashboard/src/components/ui/pagination.tsx` | Pagination, PaginationContent, PaginationEllipsis, PaginationItem, PaginationLink (+2) |

## Entry Points

Start here when exploring this area:

- **`DriftTuning`** (Function) — `dashboard/src/components/dashboard/DriftTuning.tsx:246`
- **`FlagButton`** (Function) — `dashboard/src/components/dashboard/FlagButton.tsx:20`
- **`FlaggedItemsPanel`** (Function) — `dashboard/src/components/dashboard/FlaggedItemsPanel.tsx:7`
- **`PostureStrip`** (Function) — `dashboard/src/components/dashboard/PostureStrip.tsx:71`
- **`SessionOutcomeSummary`** (Function) — `dashboard/src/components/dashboard/SessionOutcomeSummary.tsx:10`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `DriftTuning` | Function | `dashboard/src/components/dashboard/DriftTuning.tsx` | 246 |
| `FlagButton` | Function | `dashboard/src/components/dashboard/FlagButton.tsx` | 20 |
| `FlaggedItemsPanel` | Function | `dashboard/src/components/dashboard/FlaggedItemsPanel.tsx` | 7 |
| `PostureStrip` | Function | `dashboard/src/components/dashboard/PostureStrip.tsx` | 71 |
| `SessionOutcomeSummary` | Function | `dashboard/src/components/dashboard/SessionOutcomeSummary.tsx` | 10 |
| `renderTimelineRow` | Function | `dashboard/src/components/dashboard/SessionTimeline.tsx` | 1267 |
| `Sparkline` | Function | `dashboard/src/components/dashboard/Sparkline.tsx` | 8 |
| `useFlagSystem` | Function | `dashboard/src/context/useFlagSystem.ts` | 3 |
| `useIsMobile` | Function | `dashboard/src/hooks/use-mobile.tsx` | 4 |
| `sessionActivitySummary` | Function | `dashboard/src/lib/sessionHelpers.ts` | 300 |
| `timelineRowSummary` | Function | `dashboard/src/lib/sessionHelpers.ts` | 341 |
| `cn` | Function | `dashboard/src/lib/utils.ts` | 3 |
| `RuleIterationModal` | Function | `dashboard/src/components/dashboard/RuleIterationModal.tsx` | 29 |
| `handleRemoveAttachment` | Function | `dashboard/src/components/dashboard/RuleIterationModal.tsx` | 123 |
| `handleRemoveFileRef` | Function | `dashboard/src/components/dashboard/RuleIterationModal.tsx` | 99 |
| `handleSendIteration` | Function | `dashboard/src/components/dashboard/RuleIterationModal.tsx` | 211 |
| `Toaster` | Function | `dashboard/src/components/ui/toaster.tsx` | 3 |
| `NavLink` | Function | `dashboard/src/components/NavLink.tsx` | 10 |
| `CountList` | Function | `dashboard/src/components/dashboard/DriftTuning.tsx` | 72 |
| `OpsCard` | Function | `dashboard/src/components/dashboard/DriftTuning.tsx` | 101 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `RuleCommandBand → Cn` | cross_community | 5 |
| `SessionOutcomeSummary → IsAdvisoryDecision` | cross_community | 4 |
| `SessionOutcomeSummary → IsBetterCauseCandidate` | cross_community | 4 |
| `SessionOutcomeSummary → IsBlockingDecision` | cross_community | 4 |
| `App → Cn` | cross_community | 4 |
| `RuleIterationModal → Cn` | cross_community | 4 |
| `SessionRow → Cn` | intra_community | 4 |
| `RenderTimelineRow → Cn` | intra_community | 4 |
| `RuleInspector → Cn` | cross_community | 4 |
| `App → UseToast` | cross_community | 3 |

## How to Explore

1. `context({name: "DriftTuning"})` — see callers and callees
2. `query({search_query: "ui"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
