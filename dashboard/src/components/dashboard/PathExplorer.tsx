import { useState, useMemo, useCallback, memo, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Folder, FileText, ChevronRight, ChevronDown, AlertTriangle, Filter, X, Grid3X3, TreePine, Flag as FlagIcon, ChevronsUpDown, ArrowUpDown } from "lucide-react";
import type { HookEvent, RuleFinding, Decision, Severity } from "@/types/slopgate";
import { FlagButton } from "./FlagButton";
import { FlaggedItemsPanel } from "./FlaggedItemsPanel";

type PathTab = "tree" | "heatmap" | "flagged";
type SortKey = "findings" | "events" | "blocks" | "name";

interface Props {
  events: HookEvent[];
  rules: RuleFinding[];
  onPathFilter: (path: string | null) => void;
  activePathFilter: string | null;
}

interface PathNode {
  name: string;
  fullPath: string;
  eventCount: number;
  findingCount: number;
  blockCount: number;
  decisions: Partial<Record<Decision, number>>;
  severities: Partial<Record<Severity, number>>;
  rules: Record<string, number>;
  children: Map<string, PathNode>;
}

/** Build a session→events index (shared by tree and heatmap builders) */
function buildSessionIndex(events: HookEvent[]): Map<string, HookEvent[]> {
  const map = new Map<string, HookEvent[]>();
  for (const e of events) {
    if (!map.has(e.session_id)) map.set(e.session_id, []);
    map.get(e.session_id)!.push(e);
  }
  return map;
}

function buildTree(events: HookEvent[], rules: RuleFinding[], sessionIndex: Map<string, HookEvent[]>): PathNode {
  const root: PathNode = {
    name: "/", fullPath: "", eventCount: 0, findingCount: 0, blockCount: 0,
    decisions: {}, severities: {}, rules: {}, children: new Map(),
  };

  const pathFindings = new Map<string, RuleFinding[]>();
  for (const r of rules) {
    const sessionEvents = sessionIndex.get(r.session_id) || [];
    const paths = sessionEvents.flatMap(e => e.candidate_paths ?? []);
    for (const p of new Set(paths)) {
      if (!pathFindings.has(p)) pathFindings.set(p, []);
      pathFindings.get(p)!.push(r);
    }
  }

  const pathEvents = new Map<string, number>();
  for (const e of events) {
    for (const p of (e.candidate_paths ?? [])) {
      pathEvents.set(p, (pathEvents.get(p) || 0) + 1);
    }
  }

  for (const [path, count] of pathEvents) {
    const parts = path.split("/").filter(Boolean);
    let node = root;
    let fullPath = "";
    for (const part of parts) {
      fullPath += (fullPath ? "/" : "") + part;
      if (!node.children.has(part)) {
        node.children.set(part, {
          name: part, fullPath, eventCount: 0, findingCount: 0, blockCount: 0,
          decisions: {}, severities: {}, rules: {}, children: new Map(),
        });
      }
      node = node.children.get(part)!;
    }
    node.eventCount += count;
    const findings = pathFindings.get(path) || [];
    node.findingCount += findings.length;
    for (const f of findings) {
      const dec = f.decision ?? "context";
      node.decisions[dec] = (node.decisions[dec] || 0) + 1;
      node.severities[f.severity] = (node.severities[f.severity] || 0) + 1;
      node.rules[f.rule_id] = (node.rules[f.rule_id] || 0) + 1;
      if (dec === "block" || dec === "deny") node.blockCount++;
    }
  }

  function propagate(node: PathNode): { events: number; findings: number; blocks: number } {
    let ev = node.eventCount, fi = node.findingCount, bl = node.blockCount;
    for (const child of node.children.values()) {
      const c = propagate(child);
      ev += c.events; fi += c.findings; bl += c.blocks;
    }
    node.eventCount = ev; node.findingCount = fi; node.blockCount = bl;
    return { events: ev, findings: fi, blocks: bl };
  }
  propagate(root);

  return root;
}

// Heatmap data: file × time bucket — uses a Map for O(1) cell lookup
function buildHeatmapData(events: HookEvent[], rules: RuleFinding[], sessionIndex: Map<string, HookEvent[]>): {
  files: string[];
  buckets: string[];
  cellMap: Map<string, { findings: number; blocks: number }>;
} {
  const allTimestamps = rules.map(r => new Date(r.timestamp).getTime());
  if (allTimestamps.length === 0) return { files: [], buckets: [], cellMap: new Map() };
  const minT = allTimestamps.reduce((a, b) => Math.min(a, b), Infinity);
  const maxT = allTimestamps.reduce((a, b) => Math.max(a, b), -Infinity);
  const range = maxT - minT || 1;
  const bucketCount = Math.min(12, Math.max(4, Math.ceil(range / 3600000)));
  const bucketSize = range / bucketCount;

  const bucketLabels: string[] = [];
  for (let i = 0; i < bucketCount; i++) {
    const t = new Date(minT + i * bucketSize);
    bucketLabels.push(t.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "numeric" }));
  }

  const cellMap = new Map<string, { findings: number; blocks: number }>();
  const fileSet = new Set<string>();

  for (const r of rules) {
    const sessionEvents = sessionIndex.get(r.session_id) || [];
    const paths = new Set(sessionEvents.flatMap(e => e.candidate_paths ?? []));
    const t = new Date(r.timestamp).getTime();
    const bucketIdx = Math.min(bucketCount - 1, Math.floor((t - minT) / bucketSize));

    for (const p of paths) {
      fileSet.add(p);
      const key = `${bucketIdx}\x00${p}`;
      if (!cellMap.has(key)) cellMap.set(key, { findings: 0, blocks: 0 });
      const cell = cellMap.get(key)!;
      cell.findings++;
      const rdec = r.decision ?? "context";
      if (rdec === "block" || rdec === "deny") cell.blocks++;
    }
  }

  // Sort files by total findings
  const fileTotals = new Map<string, number>();
  for (const [key, val] of cellMap) {
    const file = key.slice(key.indexOf("\x00") + 1);
    fileTotals.set(file, (fileTotals.get(file) || 0) + val.findings);
  }
  // Return ALL files sorted by total findings — caller paginates
  const files = [...fileSet].sort((a, b) => (fileTotals.get(b) || 0) - (fileTotals.get(a) || 0));

  return { files, buckets: bucketLabels, cellMap };
}

const TreeRow = memo(function TreeRow({ node, depth, onPathFilter, activePathFilter, expandOverride, sortKey }: {
  node: PathNode; depth: number; onPathFilter: (path: string | null) => void; activePathFilter: string | null;
  expandOverride?: boolean | null; sortKey: SortKey;
}) {
  const [open, setOpen] = useState(depth < 1);
  const isOpen = expandOverride !== null && expandOverride !== undefined ? expandOverride : open;
  const hasChildren = node.children.size > 0;
  const isFile = !hasChildren;
  const sorted = useMemo(() => {
    const children = [...node.children.values()];
    switch (sortKey) {
      case "events": return children.sort((a, b) => b.eventCount - a.eventCount);
      case "blocks": return children.sort((a, b) => b.blockCount - a.blockCount || b.findingCount - a.findingCount);
      case "name": return children.sort((a, b) => a.name.localeCompare(b.name));
      case "findings":
      default: return children.sort((a, b) => b.findingCount - a.findingCount);
    }
  }, [node.children, sortKey]);
  const isActive = activePathFilter === node.fullPath;

  const handleClick = useCallback(() => {
    if (hasChildren) setOpen(o => !o);
  }, [hasChildren]);

  const handleFilter = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    onPathFilter(isActive ? null : node.fullPath);
  }, [onPathFilter, isActive, node.fullPath]);

  return (
    <>
      <tr
        className={cn("border-b border-border/30 hover:bg-muted/20 cursor-pointer transition-colors",
          isActive && "bg-primary/5 border-primary/20")}
        onClick={handleClick}
      >
        <td className="px-2 py-1.5" style={{ paddingLeft: `${depth * 16 + 8}px` }}>
          <div className="flex items-center gap-1.5">
            {hasChildren ? (
              isOpen ? <ChevronDown className="w-3 h-3 text-muted-foreground" /> : <ChevronRight className="w-3 h-3 text-muted-foreground" />
            ) : <span className="w-3" />}
            {isFile ? <FileText className="w-3.5 h-3.5 text-muted-foreground" /> : <Folder className="w-3.5 h-3.5 text-signal-ask" />}
            <span className={cn("text-xs", node.blockCount > 0 ? "text-signal-block font-medium" : "text-foreground")}>
              {node.name}
            </span>
            <button
              onClick={handleFilter}
              className={cn("ml-1 p-0.5 rounded transition-colors",
                isActive ? "text-primary bg-primary/10" : "text-muted-foreground/0 hover:text-primary group-hover:text-muted-foreground/50"
              )}
              title={isActive ? "Clear filter" : `Filter dashboard to ${node.fullPath}`}
            >
              {isActive ? <X className="w-3 h-3" /> : <Filter className="w-3 h-3 opacity-0 group-hover:opacity-100" />}
            </button>
            <FlagButton itemType="path" itemId={node.fullPath} label={`Path: ${node.fullPath}`} compact />
          </div>
        </td>
        <td className="px-2 py-1.5 text-right text-xs">{node.eventCount}</td>
        <td className="px-2 py-1.5 text-right text-xs">
          <span className={cn(node.findingCount > 0 ? "text-signal-ask" : "text-muted-foreground")}>{node.findingCount}</span>
        </td>
        <td className="px-2 py-1.5 text-right text-xs">
          <span className={cn(node.blockCount > 0 ? "text-signal-block font-semibold" : "text-muted-foreground")}>{node.blockCount}</span>
        </td>
        <td className="px-2 py-1.5 text-xs">
          {Object.entries(node.rules).length > 0 && (
            <div className="flex gap-1 flex-wrap max-w-[200px]">
              {Object.entries(node.rules).sort(([, a], [, b]) => b - a).slice(0, 3).map(([rule, count]) => (
                <span key={rule} className="px-1 py-0.5 bg-muted rounded text-[10px] text-muted-foreground">
                  {rule.length > 18 ? rule.slice(0, 16) + "…" : rule} ×{count}
                </span>
              ))}
            </div>
          )}
        </td>
      </tr>
      {isOpen && sorted.map(child => (
        <TreeRow key={child.fullPath} node={child} depth={depth + 1} onPathFilter={onPathFilter} activePathFilter={activePathFilter} expandOverride={expandOverride} sortKey={sortKey} />
      ))}
    </>
  );
});

const HEATMAP_PAGE_SIZE = 15;

const HeatmapView = memo(function HeatmapView({ events, rules, onPathFilter, sessionIndex }: {
  events: HookEvent[]; rules: RuleFinding[]; onPathFilter: (path: string | null) => void;
  sessionIndex: Map<string, HookEvent[]>;
}) {
  const [page, setPage] = useState(0);
  const heatmap = useMemo(() => buildHeatmapData(events, rules, sessionIndex), [events, rules, sessionIndex]);

  // Reset page when data changes
  useEffect(() => setPage(0), [heatmap]);

  const pageCount = Math.max(1, Math.ceil(heatmap.files.length / HEATMAP_PAGE_SIZE));
  const pagedFiles = heatmap.files.slice(page * HEATMAP_PAGE_SIZE, (page + 1) * HEATMAP_PAGE_SIZE);

  const maxFindings = useMemo(() => {
    let max = 1;
    for (const val of heatmap.cellMap.values()) {
      if (val.findings > max) max = val.findings;
    }
    return max;
  }, [heatmap.cellMap]);

  if (heatmap.files.length === 0) {
    return <div className="flex items-center justify-center h-48 text-muted-foreground text-xs">No finding data for heatmap</div>;
  }

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
      <table className="text-[10px] border-collapse">
        <thead>
          <tr>
            <th className="text-left px-2 py-1 text-muted-foreground sticky left-0 bg-card/90 z-10">File</th>
            {heatmap.buckets.map(b => (
              <th key={b} className="px-1 py-1 text-muted-foreground font-normal whitespace-nowrap">{b}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {pagedFiles.map((file, fileIdx) => (
            <tr key={file} className="hover:bg-muted/10">
              <td
                className="px-2 py-1 font-mono text-foreground sticky left-0 bg-card/90 z-10 cursor-pointer hover:text-primary whitespace-nowrap"
                onClick={() => onPathFilter(file)}
                title={`Filter to ${file}`}
              >
                {file}
              </td>
              {heatmap.buckets.map((bucket, bucketIdx) => {
                const cell = heatmap.cellMap.get(`${bucketIdx}\x00${file}`);
                const val = cell?.findings || 0;
                const hasBlocks = (cell?.blocks || 0) > 0;
                const intensity = val / maxFindings;
                return (
                  <td key={bucket} className="px-0.5 py-0.5">
                    <div
                      className={cn(
                        "w-8 h-6 rounded-sm flex items-center justify-center text-[9px] font-medium transition-colors",
                        val === 0 ? "bg-muted/20 text-muted-foreground/30" :
                        hasBlocks ? "text-signal-block" : "text-foreground"
                      )}
                      style={{
                        backgroundColor: val === 0 ? undefined :
                          hasBlocks ? `hsla(0, 85%, 60%, ${0.15 + intensity * 0.6})` :
                          `hsla(38, 92%, 50%, ${0.1 + intensity * 0.5})`
                      }}
                      title={`${file} @ ${bucket}: ${val} findings, ${cell?.blocks || 0} blocks`}
                    >
                      {val > 0 ? val : "·"}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      {pageCount > 1 && (
        <div className="flex items-center justify-between text-[10px] text-muted-foreground px-1 pt-1">
          <span>Showing {page * HEATMAP_PAGE_SIZE + 1}–{Math.min((page + 1) * HEATMAP_PAGE_SIZE, heatmap.files.length)} of {heatmap.files.length} files</span>
          <div className="flex gap-2">
            <button disabled={page === 0} onClick={() => setPage(p => p - 1)} className="hover:text-foreground disabled:opacity-30">← Prev</button>
            <span>{page + 1}/{pageCount}</span>
            <button disabled={page + 1 >= pageCount} onClick={() => setPage(p => p + 1)} className="hover:text-foreground disabled:opacity-30">Next →</button>
          </div>
        </div>
      )}
    </div>
  );
});

export const PathExplorer = memo(function PathExplorer({ events, rules, onPathFilter, activePathFilter }: Props) {
  const [tab, setTab] = useState<PathTab>("tree");
  const [expandOverride, setExpandOverride] = useState<boolean | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("findings");

  // Single shared session index — prevents duplicate map building
  const sessionIndex = useMemo(() => buildSessionIndex(events), [events]);

  const tree = useMemo(() => buildTree(events, rules, sessionIndex), [events, rules, sessionIndex]);
  const sorted = useMemo(() => {
    const children = [...tree.children.values()];
    switch (sortKey) {
      case "events": return children.sort((a, b) => b.eventCount - a.eventCount);
      case "blocks": return children.sort((a, b) => b.blockCount - a.blockCount || b.findingCount - a.findingCount);
      case "name": return children.sort((a, b) => a.name.localeCompare(b.name));
      case "findings":
      default: return children.sort((a, b) => b.findingCount - a.findingCount);
    }
  }, [tree, sortKey]);

  const allFiles = useMemo(() => {
    const files: PathNode[] = [];
    function collect(node: PathNode) {
      if (node.children.size === 0 && node.findingCount > 0) files.push(node);
      for (const c of node.children.values()) collect(c);
    }
    collect(tree);
    return files.sort((a, b) => b.blockCount - a.blockCount || b.findingCount - a.findingCount);
  }, [tree]);

  const blockedFileCount = useMemo(() => allFiles.filter(f => f.blockCount > 0).length, [allFiles]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-xs text-muted-foreground uppercase tracking-wider px-1 flex items-center gap-1.5">
            <Folder className="w-3.5 h-3.5" />
            Path & File Explorer
          </h3>
          {blockedFileCount > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-signal-block/10 text-signal-block flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              {blockedFileCount} files with blocks
            </span>
          )}
          {activePathFilter && (
            <button
              onClick={() => onPathFilter(null)}
              className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary"
            >
              <Filter className="w-3 h-3" />
              {activePathFilter}
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
        <div className="flex gap-1">
          {([
            { key: "tree" as PathTab, label: "Tree", icon: TreePine },
            { key: "heatmap" as PathTab, label: "Heatmap", icon: Grid3X3 },
            { key: "flagged" as PathTab, label: "Flagged", icon: FlagIcon },
          ]).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={cn(
                "px-2 py-0.5 text-[10px] rounded-sm transition-colors uppercase flex items-center gap-1",
                tab === key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
              )}
            >
              <Icon className="w-3 h-3" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Hottest files strip - only on tree tab */}
      {tab === "tree" && allFiles.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {allFiles.slice(0, 8).map(f => (
            <div
              key={f.fullPath}
              onClick={() => onPathFilter(f.fullPath)}
              className={cn(
                "px-2.5 py-1.5 rounded-md border text-[10px] font-mono cursor-pointer transition-all hover:scale-[1.02]",
                activePathFilter === f.fullPath
                  ? "border-primary bg-primary/10 text-primary ring-1 ring-primary/30"
                  : f.blockCount > 0
                  ? "border-signal-block/30 bg-signal-block/5 text-signal-block hover:border-signal-block/50"
                  : "border-border bg-card text-foreground hover:border-muted-foreground"
              )}
            >
              <div className="font-medium">{f.fullPath}</div>
              <div className="text-muted-foreground mt-0.5">
                {f.eventCount} events · {f.findingCount} findings · {f.blockCount} blocks
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Tab content */}
      {tab === "tree" && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setExpandOverride(prev => prev === true ? false : true)}
              className="flex items-center gap-1 text-[10px] px-2 py-1 rounded-sm border border-border text-muted-foreground hover:bg-muted transition-colors"
            >
              <ChevronsUpDown className="w-3 h-3" />
              {expandOverride === true ? "Collapse All" : "Expand All"}
            </button>
            {expandOverride !== null && (
              <button
                onClick={() => setExpandOverride(null)}
                className="text-[10px] px-2 py-1 rounded-sm text-muted-foreground hover:bg-muted transition-colors"
              >
                Reset
              </button>
            )}
            <div className="ml-auto flex items-center gap-1">
              <ArrowUpDown className="w-3 h-3 text-muted-foreground" />
              {(["findings", "blocks", "events", "name"] as SortKey[]).map(k => (
                <button
                  key={k}
                  onClick={() => setSortKey(k)}
                  className={cn(
                    "px-2 py-0.5 text-[10px] rounded-sm transition-colors capitalize",
                    sortKey === k ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
                  )}
                >
                  {k}
                </button>
              ))}
            </div>
          </div>
          <div className="border border-border rounded-md bg-card/30 overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-muted-foreground text-[10px] uppercase">
                  <th className="px-2 py-2 text-left">Path</th>
                  <th className="px-2 py-2 text-right w-20">Events</th>
                  <th className="px-2 py-2 text-right w-20">Findings</th>
                  <th className="px-2 py-2 text-right w-20">Blocks</th>
                  <th className="px-2 py-2 text-left">Top Rules</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map(node => (
                  <TreeRow key={node.fullPath} node={node} depth={0} onPathFilter={onPathFilter} activePathFilter={activePathFilter} expandOverride={expandOverride} sortKey={sortKey} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "heatmap" && (
        <div className="border border-border rounded-md bg-card/30 p-3 overflow-hidden">
          <HeatmapView events={events} rules={rules} onPathFilter={onPathFilter} sessionIndex={sessionIndex} />
        </div>
      )}

      {tab === "flagged" && (
        <div className="border border-border rounded-md bg-card/30 p-3">
          <FlaggedItemsPanel />
        </div>
      )}
    </div>
  );
});