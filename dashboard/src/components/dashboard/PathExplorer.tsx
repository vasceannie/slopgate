import {
	AlertTriangle,
	ArrowUpDown,
	CheckCircle2,
	ChevronDown,
	ChevronRight,
	ChevronsUpDown,
	FileText,
	Filter,
	Flag as FlagIcon,
	Folder,
	Grid3X3,
	Plus,
	RotateCcw,
	Save,
	Settings,
	Sparkles,
	TreePine,
	X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { RuleIterationModal } from "./RuleIterationModal";
import { useRulesConfig } from "@/context/useRulesConfig";
import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import type {
	Decision,
	HookEvent,
	RuleFinding,
	Severity,
} from "@/types/slopgate";
import { FlagButton } from "./FlagButton";
import { FlaggedItemsPanel } from "./FlaggedItemsPanel";

type PathTab = "tree" | "heatmap" | "flagged";
type SortKey = "findings" | "events" | "blocks" | "name" | "alpha";

interface Props {
	events: HookEvent[];
	rules: RuleFinding[];
	onPathFilter: (path: string | null) => void;
	activePathFilter: string | null;
	onOpenRules?: () => void;
	onOpenOps?: () => void;
	defaultTab?: "control-room" | "telemetry" | "recommendations";
}

type SelectedRepoKey = string | "all" | "outside_repo";

interface RepoOption {
	key: string;
	label: string;
	repoRoot: string | null;
	mode: "all" | "repo" | "outside_repo";
	events: HookEvent[];
	rules: RuleFinding[];
	tree?: PathNode;
	sorted?: PathNode[];
}

interface PathNode {
	name: string;
	fullPath: string;
	filterPath: string;
	eventCount: number;
	findingCount: number;
	blockCount: number;
	eventIds: Set<string>;
	findingIds: Set<string>;
	blockFindingIds: Set<string>;
	decisions: Partial<Record<Decision, number>>;
	severities: Partial<Record<Severity, number>>;
	rules: Record<string, number>;
	children: Map<string, PathNode>;
}

interface ScopedPath {
	displayPath: string;
	filterPath: string;
}

const COMMON_EXTENSIONS = new Set([
	"py",
	"pyi",
	"js",
	"jsx",
	"ts",
	"tsx",
	"json",
	"md",
	"sh",
	"yml",
	"yaml",
	"toml",
	"rs",
	"go",
	"java",
	"c",
	"h",
	"cpp",
	"css",
	"html",
	"txt",
	"diff",
	"patch",
	"lock",
]);

const ALLOWED_SINGLE_WORDS = new Set([
	"makefile",
	"license",
	"readme",
	"dockerfile",
]);

function isValidPath(p: string): boolean {
	if (!p) return false;

	if (!/^[A-Za-z0-9_./\-@]+$/.test(p)) return false;

	const segments = p.split("/").filter(Boolean);
	if (segments.length === 0) return false;

	const filename = segments[segments.length - 1];

	if (segments.length === 1 && !filename.includes(".")) {
		if (/^\d+$/.test(filename)) return false;

		const lower = filename.toLowerCase();
		if (ALLOWED_SINGLE_WORDS.has(lower)) return true;

		if (filename !== lower) return false;
	}

	const parts = filename.split(".");
	if (parts.length > 1) {
		const ext = parts[parts.length - 1].toLowerCase();
		if (!COMMON_EXTENSIONS.has(ext)) return false;
	}
	return true;
}

function createPathNode(name: string, fullPath: string, filterPath: string): PathNode {
	return {
		name,
		fullPath,
		filterPath,
		eventCount: 0,
		findingCount: 0,
		blockCount: 0,
		eventIds: new Set(),
		findingIds: new Set(),
		blockFindingIds: new Set(),
		decisions: {},
		severities: {},
		rules: {},
		children: new Map(),
	};
}

function cleanPathSegments(path: string): string[] {
	return path.split("/").filter((part) => part && part !== ".");
}

function trimTrailingSlash(path: string): string {
	return path.replace(/\/+$/, "");
}

function isAbsolutePath(path: string): boolean {
	return path.startsWith("/") || /^[A-Za-z]:[\\/]/.test(path);
}

function compactUnscopedPath(path: string): string {
	const segments = cleanPathSegments(path);
	if (segments.length <= 3) return segments.join("/");

	for (const marker of ["repos", "workspace-hooker", "worktrees", "projects"]) {
		const markerIndex = segments.indexOf(marker);
		if (markerIndex >= 0 && markerIndex + 1 < segments.length) {
			return segments.slice(markerIndex + 1).join("/");
		}
	}

	return segments.slice(-3).join("/");
}

function normalizePath(p: string, repoRoot?: string | null): ScopedPath | null {
	const rawPath = p.trim();
	if (!rawPath) return null;

	if (repoRoot) {
		const root = trimTrailingSlash(repoRoot.trim());
		if (!root) return null;
		if (rawPath === root) return null;

		if (rawPath.startsWith(`${root}/`)) {
			const displayPath = cleanPathSegments(rawPath.slice(root.length)).join("/");
			return displayPath ? { displayPath, filterPath: rawPath } : null;
		}

		if (isAbsolutePath(rawPath)) return null;
	}

	const displayPath = isAbsolutePath(rawPath)
		? compactUnscopedPath(rawPath)
		: cleanPathSegments(rawPath).join("/");
	return displayPath ? { displayPath, filterPath: rawPath } : null;
}

function pathMatchesQuery(path: ScopedPath, query: string): boolean {
	const normalized = path.displayPath.toLowerCase();
	if (query.startsWith(".")) return normalized.endsWith(query);
	return normalized.includes(query);
}

function eventKey(event: HookEvent, index: number): string {
	return `${event.session_id}\x00${event.timestamp}\x00${event.event_name}\x00${event.tool_name}\x00${index}`;
}

function findingKey(finding: RuleFinding, index: number): string {
	return `${finding.session_id}\x00${finding.timestamp}\x00${finding.rule_id}\x00${finding.decision ?? "context"}\x00${index}`;
}

function sortAlpha(children: PathNode[]): PathNode[] {
	return [...children].sort((a, b) => {
		const aIsDir = a.children.size > 0;
		const bIsDir = b.children.size > 0;
		if (aIsDir !== bIsDir) return aIsDir ? -1 : 1;
		return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
	});
}

/** Build a session→events index (shared by tree and heatmap builders) */
function buildSessionIndex(events: HookEvent[]): Map<string, HookEvent[]> {
	const map = new Map<string, HookEvent[]>();
	for (const e of events) {
		if (!map.has(e.session_id)) map.set(e.session_id, []);
		map.get(e.session_id)?.push(e);
	}
	return map;
}

function buildTree(
	events: HookEvent[],
	rules: RuleFinding[],
	sessionIndex: Map<string, HookEvent[]>,
	repoRoot?: string | null,
): PathNode {
	const root = createPathNode("/", "", repoRoot ?? "");

	const resolvePath = (path: string): ScopedPath | null => normalizePath(path, repoRoot);

	const sessionPaths = new Map<string, string[]>();
	const neededSessions = new Set(rules.map((r) => r.session_id));
	for (const sessionId of neededSessions) {
		const sessionEvs = sessionIndex.get(sessionId) || [];
		const paths = sessionEvs
			.flatMap((e) => e.candidate_paths ?? [])
			.map(resolvePath)
			.filter((path): path is ScopedPath =>
				Boolean(path && isValidPath(path.displayPath)),
			)
			.map((path) => path.displayPath);
		sessionPaths.set(sessionId, [...new Set(paths)]);
	}

	const pathFindings = new Map<
		string,
		Array<{ finding: RuleFinding; key: string }>
	>();
	for (const [index, r] of rules.entries()) {
		const paths = sessionPaths.get(r.session_id) || [];
		const key = findingKey(r, index);
		for (const p of paths) {
			if (!pathFindings.has(p)) pathFindings.set(p, []);
			pathFindings.get(p)?.push({ finding: r, key });
		}
	}

	const pathEvents = new Map<string, { filterPath: string; eventIds: Set<string> }>();
	for (const [index, e] of events.entries()) {
		const key = eventKey(e, index);
		for (const scopedPath of (e.candidate_paths ?? [])
			.map(resolvePath)
			.filter((path): path is ScopedPath =>
				Boolean(path && isValidPath(path.displayPath)),
			)) {
			const bucket = pathEvents.get(scopedPath.displayPath) ?? {
				filterPath: scopedPath.filterPath,
				eventIds: new Set<string>(),
			};
			bucket.eventIds.add(key);
			pathEvents.set(scopedPath.displayPath, bucket);
		}
	}

	for (const [path, { filterPath, eventIds }] of pathEvents) {
		const parts = path.split("/").filter(Boolean);
		let node = root;
		let fullPath = "";
		let currentFilterPath = "";
		for (const [index, part] of parts.entries()) {
			fullPath += (fullPath ? "/" : "") + part;
			currentFilterPath =
				index === parts.length - 1
					? filterPath
					: repoRoot
						? `${trimTrailingSlash(repoRoot)}/${fullPath}`
						: fullPath;
			let child = node.children.get(part);
			if (!child) {
				child = createPathNode(part, fullPath, currentFilterPath);
				node.children.set(part, child);
			}
			node = child;
		}
		for (const eventId of eventIds) node.eventIds.add(eventId);
		const findings = pathFindings.get(path) || [];
		for (const { finding: f, key } of findings) {
			node.findingIds.add(key);
			const dec = f.decision ?? "context";
			node.decisions[dec] = (node.decisions[dec] || 0) + 1;
			node.severities[f.severity] = (node.severities[f.severity] || 0) + 1;
			node.rules[f.rule_id] = (node.rules[f.rule_id] || 0) + 1;
			if (dec === "block" || dec === "deny") node.blockFindingIds.add(key);
		}
	}

	function propagate(node: PathNode): {
		events: Set<string>;
		findings: Set<string>;
		blocks: Set<string>;
	} {
		for (const child of node.children.values()) {
			const c = propagate(child);
			for (const eventId of c.events) node.eventIds.add(eventId);
			for (const findingId of c.findings) node.findingIds.add(findingId);
			for (const blockFindingId of c.blocks) {
				node.blockFindingIds.add(blockFindingId);
			}
		}
		node.eventCount = node.eventIds.size;
		node.findingCount = node.findingIds.size;
		node.blockCount = node.blockFindingIds.size;
		return {
			events: node.eventIds,
			findings: node.findingIds,
			blocks: node.blockFindingIds,
		};
	}
	propagate(root);

	return root;
}

// Heatmap data: file × time bucket — uses a Map for O(1) cell lookup
function buildHeatmapData(
	_events: HookEvent[],
	rules: RuleFinding[],
	sessionIndex: Map<string, HookEvent[]>,
): {
	files: string[];
	filterPaths: Map<string, string>;
	buckets: string[];
	cellMap: Map<string, { findings: number; blocks: number }>;
} {
	const allTimestamps = rules.map((r) => new Date(r.timestamp).getTime());
	if (allTimestamps.length === 0)
		return { files: [], filterPaths: new Map(), buckets: [], cellMap: new Map() };
	const minT = allTimestamps.reduce((a, b) => Math.min(a, b), Infinity);
	const maxT = allTimestamps.reduce((a, b) => Math.max(a, b), -Infinity);
	const range = maxT - minT || 1;
	const bucketCount = Math.min(12, Math.max(4, Math.ceil(range / 3600000)));
	const bucketSize = range / bucketCount;

	const bucketLabels: string[] = [];
	for (let i = 0; i < bucketCount; i++) {
		const t = new Date(minT + i * bucketSize);
		bucketLabels.push(
			t.toLocaleDateString("en-US", {
				month: "short",
				day: "numeric",
				hour: "numeric",
			}),
		);
	}

	const cellMap = new Map<string, { findings: number; blocks: number }>();
	const fileSet = new Set<string>();
	const fileFilterPaths = new Map<string, string>();
	const sessionRepoRoots = new Map<string, string | null | undefined>();
	for (const rule of rules) {
		if (!sessionRepoRoots.has(rule.session_id)) {
			sessionRepoRoots.set(rule.session_id, rule.resolved_repo_root);
		}
	}

	const sessionPaths = new Map<string, Set<string>>();
	const neededSessions = new Set(rules.map((r) => r.session_id));
	for (const sessionId of neededSessions) {
		const sessionEvents = sessionIndex.get(sessionId) || [];
		const repoRoot =
			sessionEvents.find((event) => event.resolved_repo_root)?.resolved_repo_root ??
			sessionRepoRoots.get(sessionId);
		const scopedPaths = sessionEvents
			.flatMap((e) => e.candidate_paths ?? [])
			.map((path) => normalizePath(path, repoRoot))
			.filter((path): path is ScopedPath =>
				Boolean(path && isValidPath(path.displayPath)),
			);
		for (const scopedPath of scopedPaths) {
			if (!fileFilterPaths.has(scopedPath.displayPath)) {
				fileFilterPaths.set(scopedPath.displayPath, scopedPath.filterPath);
			}
		}
		sessionPaths.set(
			sessionId,
			new Set(scopedPaths.map((path) => path.displayPath)),
		);
	}

	for (const r of rules) {
		const paths = sessionPaths.get(r.session_id) || new Set<string>();
		const t = new Date(r.timestamp).getTime();
		const bucketIdx = Math.min(
			bucketCount - 1,
			Math.floor((t - minT) / bucketSize),
		);

		for (const p of paths) {
			fileSet.add(p);
			const key = `${bucketIdx}\x00${p}`;
			let cell = cellMap.get(key);
			if (!cell) {
				cell = { findings: 0, blocks: 0 };
				cellMap.set(key, cell);
			}
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
	const files = [...fileSet].sort(
		(a, b) => (fileTotals.get(b) || 0) - (fileTotals.get(a) || 0),
	);

	return { files, filterPaths: fileFilterPaths, buckets: bucketLabels, cellMap };
}

const TreeRow = memo(function TreeRow({
	node,
	depth,
	onPathFilter,
	activePathFilter,
	expandOverride,
	sortKey,
	repoRoot,
}: {
	node: PathNode;
	depth: number;
	onPathFilter: (path: string | null) => void;
	activePathFilter: string | null;
	expandOverride?: boolean | null;
	sortKey: SortKey;
	repoRoot?: string | null;
}) {
	const [open, setOpen] = useState(false);
	const isOpen =
		expandOverride !== null && expandOverride !== undefined
			? expandOverride
			: open;
	const hasChildren = node.children.size > 0;
	const isFile = !hasChildren;
	const sorted = useMemo(() => {
		const children = [...node.children.values()];
		switch (sortKey) {
			case "events":
				return children.sort((a, b) => b.eventCount - a.eventCount);
			case "blocks":
				return children.sort(
					(a, b) =>
						b.blockCount - a.blockCount || b.findingCount - a.findingCount,
				);
			case "name":
				return children.sort((a, b) => a.name.localeCompare(b.name));
			case "alpha":
				return sortAlpha(children);
			default:
				return children.sort((a, b) => b.findingCount - a.findingCount);
		}
	}, [node.children, sortKey]);
	const absolutePath = repoRoot
		? node.filterPath
		: node.filterPath || node.fullPath;
	const isActive = activePathFilter === absolutePath;

	const handleClick = useCallback(() => {
		if (hasChildren) setOpen((o) => !o);
	}, [hasChildren]);

	const handleFilter = useCallback(
		(e: React.MouseEvent) => {
			e.stopPropagation();
			onPathFilter(isActive ? null : absolutePath);
		},
		[onPathFilter, isActive, absolutePath],
	);

	return (
		<>
			<tr
				className={cn(
					"border-b border-border/30 hover:bg-muted/10 transition-colors animate-fade-in",
					isActive && "bg-primary/5 border-primary/20",
				)}
			>
				<td
					className="px-2 py-1.5 text-xs text-left"
					style={{ paddingLeft: `${depth * 16 + 8}px` }}
				>
					<div className="flex items-center gap-1.5">
						{hasChildren ? (
							<button
								type="button"
								onClick={(e) => {
									e.stopPropagation();
									handleClick();
								}}
								className="p-0.5 hover:bg-muted rounded text-muted-foreground focus:outline-none focus-visible:ring-1 focus-visible:ring-primary/80 transition-transform duration-200"
								aria-label={isOpen ? "Collapse directory" : "Expand directory"}
							>
								<ChevronRight
									className={cn(
										"w-3.5 h-3.5 transition-transform duration-200 ease-out-quart motion-reduce:transition-none",
										isOpen && "transform rotate-90"
									)}
								/>
							</button>
						) : (
							<span className="w-4.5" />
						)}
						{isFile ? (
							<FileText className="w-3.5 h-3.5 text-muted-foreground/80" />
						) : (
							<Folder className="w-3.5 h-3.5 text-signal-ask/90" />
						)}
						<button
							type="button"
							onClick={(e) => {
								e.stopPropagation();
								if (hasChildren) {
									handleClick();
								} else {
									onPathFilter(isActive ? null : absolutePath);
								}
							}}
							className={cn(
								"font-mono text-left focus:outline-none focus-visible:ring-1 focus-visible:ring-primary/80 rounded px-1 py-0.5 hover:text-primary transition-colors select-text",
								node.blockCount > 0
									? "text-signal-block font-semibold"
									: "text-foreground",
								isActive && "text-primary font-bold bg-primary/5 border border-primary/20"
							)}
						>
							{node.name}
						</button>
					</div>
				</td>
				<td className="px-2 py-1.5 text-right text-xs font-mono text-muted-foreground/90">
					<span key={node.eventCount} className="animate-count-pulse">
						{node.eventCount}
					</span>
				</td>
				<td className="px-2 py-1.5 text-right text-xs font-mono">
					<span
						key={node.findingCount}
						className={cn(
							"animate-count-pulse",
							node.findingCount > 0
								? "text-signal-ask font-medium"
								: "text-muted-foreground/60",
						)}
					>
						{node.findingCount}
					</span>
				</td>
				<td className="px-2 py-1.5 text-right text-xs font-mono">
					<span
						key={node.blockCount}
						className={cn(
							"animate-count-pulse",
							node.blockCount > 0
								? "text-signal-block font-semibold"
								: "text-muted-foreground/60",
						)}
					>
						{node.blockCount}
					</span>
				</td>
				<td className="px-2 py-1.5 text-center text-xs w-24">
					<div className="flex items-center justify-center gap-1.5">
						<button
							type="button"
							onClick={handleFilter}
							className={cn(
								"p-1 rounded transition-all focus:outline-none focus-visible:ring-1 focus-visible:ring-primary border",
								isActive
									? "text-primary bg-primary/10 border-primary/20 hover:bg-primary/20"
									: "text-muted-foreground/80 border-border/40 hover:text-primary hover:bg-muted/40"
							)}
							title={
								isActive
									? "Clear filter"
									: `Filter dashboard to ${absolutePath}`
							}
						>
							{isActive ? (
								<X className="w-3.5 h-3.5" />
							) : (
								<Filter className="w-3.5 h-3.5" />
							)}
						</button>
						<FlagButton
							itemType="path"
							itemId={absolutePath}
							label={`Path: ${node.fullPath}`}
							compact
						/>
					</div>
				</td>
				<td className="px-2 py-1.5 text-xs">
					{Object.entries(node.rules).length > 0 && (
						<div className="flex gap-1 flex-wrap max-w-[220px]">
							{Object.entries(node.rules)
								.sort(([, a], [, b]) => b - a)
								.slice(0, 3)
								.map(([rule, count]) => (
									<span
										key={rule}
										className="px-1.5 py-0.5 bg-muted/60 border border-border/30 rounded-sm text-xs text-muted-foreground font-mono transition-all hover:bg-muted hover:text-foreground"
										title={`${rule}: ${count} findings`}
									>
										{rule.length > 18 ? `${rule.slice(0, 16)}…` : rule} ×{count}
									</span>
								))}
						</div>
					)}
				</td>
			</tr>
			{isOpen && (
				<TreeRowsList
					sorted={sorted}
					depth={depth + 1}
					onPathFilter={onPathFilter}
					activePathFilter={activePathFilter}
					expandOverride={expandOverride}
					sortKey={sortKey}
					repoRoot={repoRoot}
				/>
			)}
		</>
	);
});

const TreeRowsList = memo(function TreeRowsList({
	sorted,
	depth,
	onPathFilter,
	activePathFilter,
	expandOverride,
	sortKey,
	repoRoot,
}: {
	sorted: PathNode[];
	depth: number;
	onPathFilter: (path: string | null) => void;
	activePathFilter: string | null;
	expandOverride?: boolean | null;
	sortKey: SortKey;
	repoRoot?: string | null;
}) {
	const [visibleCount, setVisibleCount] = useState(50);

	useEffect(() => {
		setVisibleCount(50);
	}, []);

	return (
		<>
			{sorted.slice(0, visibleCount).map((child) => (
				<TreeRow
					key={child.fullPath}
					node={child}
					depth={depth}
					onPathFilter={onPathFilter}
					activePathFilter={activePathFilter}
					expandOverride={expandOverride}
					sortKey={sortKey}
					repoRoot={repoRoot}
				/>
			))}
			{sorted.length > visibleCount && (
				<tr>
					<td
						colSpan={6}
						className="px-2 py-1.5 text-xs text-muted-foreground"
						style={{ paddingLeft: `${depth * 16 + 8}px` }}
					>
						<button
							type="button"
							className="flex items-center gap-1.5 hover:text-foreground transition-colors select-none"
							onClick={(e) => {
								e.stopPropagation();
								setVisibleCount((c) => c + 100);
							}}
						>
							<ChevronsUpDown className="w-3.5 h-3.5" />
							<span>
								Showing {visibleCount} of {sorted.length} items. Click to load
								100 more...
							</span>
						</button>
					</td>
				</tr>
			)}
		</>
	);
});

const HEATMAP_PAGE_SIZE = 15;

const HeatmapView = memo(function HeatmapView({
	events,
	rules,
	onPathFilter,
	sessionIndex,
}: {
	events: HookEvent[];
	rules: RuleFinding[];
	onPathFilter: (path: string | null) => void;
	sessionIndex: Map<string, HookEvent[]>;
}) {
	const [page, setPage] = useState(0);
	const heatmap = useMemo(
		() => buildHeatmapData(events, rules, sessionIndex),
		[events, rules, sessionIndex],
	);

	// Reset page when data changes
	useEffect(() => setPage(0), []);

	const pageCount = Math.max(
		1,
		Math.ceil(heatmap.files.length / HEATMAP_PAGE_SIZE),
	);
	const pagedFiles = heatmap.files.slice(
		page * HEATMAP_PAGE_SIZE,
		(page + 1) * HEATMAP_PAGE_SIZE,
	);

	const maxFindings = useMemo(() => {
		let max = 1;
		for (const val of heatmap.cellMap.values()) {
			if (val.findings > max) max = val.findings;
		}
		return max;
	}, [heatmap.cellMap]);

	if (heatmap.files.length === 0) {
		return (
			<div className="flex items-center justify-center h-48 text-muted-foreground text-xs">
				No finding data for heatmap
			</div>
		);
	}

	return (
		<div className="space-y-2">
			<div className="overflow-x-auto">
				<table className="text-xs border-collapse">
					<thead>
						<tr>
							<th className="text-left px-2 py-1 text-muted-foreground sticky left-0 bg-card/90 z-10">
								File
							</th>
							{heatmap.buckets.map((b) => (
								<th
									key={b}
									className="px-1 py-1 text-muted-foreground font-normal whitespace-nowrap"
								>
									{b}
								</th>
							))}
						</tr>
					</thead>
					<tbody>
						{pagedFiles.map((file) => (
							<tr key={file} className="hover:bg-muted/10">
								<td className="px-2 py-1 sticky left-0 bg-card/90 z-10 whitespace-nowrap">
									<button
										type="button"
										className="font-mono text-foreground hover:text-primary"
										onClick={() => onPathFilter(heatmap.filterPaths.get(file) ?? file)}
										title={`Filter to ${heatmap.filterPaths.get(file) ?? file}`}
									>
										{file}
									</button>
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
													"w-8 h-6 rounded-sm flex items-center justify-center text-xs font-medium transition-colors",
													val === 0
														? "bg-muted/20 text-muted-foreground/30"
														: hasBlocks
															? "text-signal-block"
															: "text-foreground",
												)}
												style={{
													backgroundColor:
														val === 0
															? undefined
															: hasBlocks
																? `hsla(0, 85%, 60%, ${0.15 + intensity * 0.6})`
																: `hsla(38, 92%, 50%, ${0.1 + intensity * 0.5})`,
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
				<div className="flex items-center justify-between text-xs text-muted-foreground px-1 pt-1">
					<span>
						Showing {page * HEATMAP_PAGE_SIZE + 1}–
						{Math.min((page + 1) * HEATMAP_PAGE_SIZE, heatmap.files.length)} of{" "}
						{heatmap.files.length} files
					</span>
					<div className="flex gap-2">
						<button
							type="button"
							disabled={page === 0}
							onClick={() => setPage((p) => p - 1)}
							className="hover:text-foreground disabled:opacity-30"
						>
							← Prev
						</button>
						<span>
							{page + 1}/{pageCount}
						</span>
						<button
							type="button"
							disabled={page + 1 >= pageCount}
							onClick={() => setPage((p) => p + 1)}
							className="hover:text-foreground disabled:opacity-30"
						>
							Next →
						</button>
					</div>
				</div>
			)}
		</div>
	);
});

export const PathExplorer = memo(function PathExplorer({
	events,
	rules,
	onPathFilter,
	activePathFilter,
	defaultTab,
}: Props) {
	const [selectedRepoKey, setSelectedRepoKey] = useState<SelectedRepoKey>("all");
	const [activeExplorerTab, setActiveExplorerTab] = useState<"overview" | "telemetry" | "recommendations">(() => {
		if (defaultTab === "control-room") return "overview";
		return defaultTab ?? "overview";
	});
	const [tab, setTab] = useState<PathTab>("tree");
	const [expandOverride, setExpandOverride] = useState<boolean | null>(null);
	const [sortKey, setSortKey] = useState<SortKey>("alpha");
	const [nonSlopgateExpanded, setNonSlopgateExpanded] = useState(false);
	const [searchQuery, setSearchQuery] = useState("");
	const [newSkipPath, setNewSkipPath] = useState("");
	const [isRuleModalOpen, setIsRuleModalOpen] = useState(false);

	// Glob test state
	const [testPathInput, setTestPathInput] = useState("");
	const [testResult, setTestResult] = useState<{ matches: boolean; glob: string | null } | null>(null);

	const {
		config,
		pendingCount,
		setSkipPaths,
		saveConfig,
		discardChanges,
		saveStatus,
		saveError,
	} = useRulesConfig();

	// Single shared session index — prevents duplicate map building
	const sessionIndex = useMemo(() => buildSessionIndex(events), [events]);

	const filteredEvents = useMemo(() => {
		if (!searchQuery) return events;
		const q = searchQuery.toLowerCase().trim();
		return events.filter((e) => {
			const repoRoot = e.enforcement_mode === "outside_repo"
				? null
				: e.resolved_repo_root;
			return (e.candidate_paths ?? [])
				.map((path) => normalizePath(path, repoRoot))
				.some((path) => path !== null && pathMatchesQuery(path, q));
		});
	}, [events, searchQuery]);

	const filteredRules = useMemo(() => {
		if (!searchQuery) return rules;
		const q = searchQuery.toLowerCase().trim();
		return rules.filter((r) => {
			if (r.rule_id.toLowerCase().includes(q)) return true;
			if (r.decision?.toLowerCase() === q) return true;
			if (r.severity?.toLowerCase() === q) return true;

			const sessionEvs = sessionIndex.get(r.session_id) || [];
			return sessionEvs.some((event) => {
				const repoRoot = event.enforcement_mode === "outside_repo"
					? null
					: event.resolved_repo_root ?? r.resolved_repo_root;
				return (event.candidate_paths ?? [])
					.map((path) => normalizePath(path, repoRoot))
					.some((path) => path !== null && pathMatchesQuery(path, q));
			});
		});
	}, [rules, searchQuery, sessionIndex]);

	const { filteredEventsCount, filteredFindingsCount, filteredBlocksCount } = useMemo(() => {
		const targetEvents = searchQuery ? filteredEvents : events;
		const targetRules = searchQuery ? filteredRules : rules;
		return {
			filteredEventsCount: targetEvents.length,
			filteredFindingsCount: targetRules.length,
			filteredBlocksCount: targetRules.filter(
				(r) => r.decision === "block" || r.decision === "deny",
			).length,
		};
	}, [events, rules, searchQuery, filteredEvents, filteredRules]);

	const sessionMeta = useMemo(() => {
		const meta = new Map<
			string,
			{ resolved_repo_root?: string | null; enforcement_mode?: string | null }
		>();
		for (const e of events) {
			const existing = meta.get(e.session_id) ?? {};
			meta.set(e.session_id, existing);
			if (e.resolved_repo_root && !existing.resolved_repo_root) {
				existing.resolved_repo_root = e.resolved_repo_root;
			}
			if (e.enforcement_mode && !existing.enforcement_mode) {
				existing.enforcement_mode = e.enforcement_mode;
			}
		}
		for (const r of rules) {
			const existing = meta.get(r.session_id) ?? {};
			meta.set(r.session_id, existing);
			if (r.resolved_repo_root && !existing.resolved_repo_root) {
				existing.resolved_repo_root = r.resolved_repo_root;
			}
			if (r.enforcement_mode && !existing.enforcement_mode) {
				existing.enforcement_mode = r.enforcement_mode;
			}
		}
		return meta;
	}, [events, rules]);

	const getProjectInfo = useCallback(
		(sid: string) => {
			const meta = sessionMeta.get(sid);
			if (!meta?.resolved_repo_root)
				return { isSlopgate: false, repoRoot: null, projectName: null };
			const isSlopgate = meta.enforcement_mode !== "outside_repo";
			const repoRoot = meta.resolved_repo_root;
			const segments = repoRoot.split("/").filter(Boolean);
			const projectName =
				segments.length > 0 ? segments[segments.length - 1] : "unknown-project";
			return { isSlopgate, repoRoot, projectName };
		},
		[sessionMeta],
	);

	const { projectGroups, nonSlopgateGroup } = useMemo(() => {
		const projectMap = new Map<
			string,
			{
				repoRoot: string;
				projectName: string;
				events: HookEvent[];
				rules: RuleFinding[];
			}
		>();
		const nonSlop: { events: HookEvent[]; rules: RuleFinding[] } = {
			events: [],
			rules: [],
		};

		for (const e of filteredEvents) {
			const { isSlopgate, repoRoot, projectName } = getProjectInfo(
				e.session_id,
			);
			if (isSlopgate && repoRoot && projectName) {
				if (!projectMap.has(repoRoot)) {
					projectMap.set(repoRoot, {
						repoRoot,
						projectName,
						events: [],
						rules: [],
					});
				}
				projectMap.get(repoRoot)?.events.push(e);
			} else {
				nonSlop.events.push(e);
			}
		}

		for (const r of filteredRules) {
			const { isSlopgate, repoRoot } = getProjectInfo(r.session_id);
			if (isSlopgate && repoRoot) {
				const proj = projectMap.get(repoRoot);
				if (proj) {
					proj.rules.push(r);
				}
			} else {
				nonSlop.rules.push(r);
			}
		}

		return {
			projectGroups: Array.from(projectMap.values()),
			nonSlopgateGroup: nonSlop,
		};
	}, [filteredEvents, filteredRules, getProjectInfo]);

	const projectTrees = useMemo(() => {
		return projectGroups.map((proj) => {
			const tree = buildTree(
				proj.events,
				proj.rules,
				sessionIndex,
				proj.repoRoot,
			);
			const children = [...tree.children.values()];
			const getSorted = (childrenList: PathNode[]) => {
				switch (sortKey) {
					case "events":
						return childrenList.sort((a, b) => b.eventCount - a.eventCount);
					case "blocks":
						return childrenList.sort(
							(a, b) =>
								b.blockCount - a.blockCount || b.findingCount - a.findingCount,
						);
					case "name":
						return childrenList.sort((a, b) => a.name.localeCompare(b.name));
					case "alpha":
						return sortAlpha(childrenList);
					default:
						return childrenList.sort((a, b) => b.findingCount - a.findingCount);
				}
			};
			return {
				...proj,
				tree,
				sorted: getSorted(children),
			};
		});
	}, [projectGroups, sessionIndex, sortKey]);

	const nonSlopgateTree = useMemo(() => {
		if (
			nonSlopgateGroup.events.length === 0 &&
			nonSlopgateGroup.rules.length === 0
		)
			return null;
		const tree = buildTree(
			nonSlopgateGroup.events,
			nonSlopgateGroup.rules,
			sessionIndex,
			null,
		);
		const children = [...tree.children.values()];
		const getSorted = (childrenList: PathNode[]) => {
			switch (sortKey) {
				case "events":
					return childrenList.sort((a, b) => b.eventCount - a.eventCount);
				case "blocks":
					return childrenList.sort(
						(a, b) =>
							b.blockCount - a.blockCount || b.findingCount - a.findingCount,
					);
				case "name":
					return childrenList.sort((a, b) => a.name.localeCompare(b.name));
				case "alpha":
					return sortAlpha(childrenList);
				default:
					return childrenList.sort((a, b) => b.findingCount - a.findingCount);
			}
		};
		return {
			tree,
			sorted: getSorted(children),
		};
	}, [nonSlopgateGroup, sessionIndex, sortKey]);

	const allFiles = useMemo(() => {
		const files: { node: PathNode; repoRoot: string | null }[] = [];
		function collect(node: PathNode, repoRoot: string | null) {
			if (node.children.size === 0 && node.findingCount > 0) {
				files.push({ node, repoRoot });
			}
			for (const c of node.children.values()) collect(c, repoRoot);
		}
		for (const proj of projectTrees) {
			collect(proj.tree, proj.repoRoot);
		}
		if (nonSlopgateTree) {
			collect(nonSlopgateTree.tree, null);
		}
		return files.sort(
			(a, b) =>
				b.node.blockCount - a.node.blockCount ||
				b.node.findingCount - a.node.findingCount,
		);
	}, [projectTrees, nonSlopgateTree]);

	const blockedFileCount = useMemo(
		() => allFiles.filter((f) => f.node.blockCount > 0).length,
		[allFiles],
	);

	const getRepoEnforcementMode = useCallback((repoRoot: string): string => {
		const repoEvents = events.filter((e) => e.resolved_repo_root === repoRoot);
		for (const e of repoEvents) {
			if (e.enforcement_mode) return e.enforcement_mode;
		}
		return "repo_strict";
	}, [events]);

	const matchesGlob = useCallback((path: string, glob: string): boolean => {
		const cleanPath = path.trim();
		const cleanGlob = glob.trim();
		if (!cleanGlob) return false;

		try {
			let regexStr = cleanGlob.replace(/[.+^${}()|\\+]/g, "\\$&");
			const doublePlaceholder = "___DBL_AST___";
			regexStr = regexStr.replace(/\*\*/g, doublePlaceholder);
			regexStr = regexStr.replace(/\*/g, "[^/]*");
			regexStr = regexStr.replace(new RegExp(doublePlaceholder, "g"), ".*");
			
			if (!cleanGlob.includes("/")) {
				const regex = new RegExp(`(^|/)${regexStr}($|/)`);
				return regex.test(cleanPath);
			}
			const regex = new RegExp(`^${regexStr}$`);
			return regex.test(cleanPath);
		} catch {
			return false;
		}
	}, []);

	const handleTestPath = useCallback(() => {
		const path = testPathInput.trim();
		if (!path || !config) {
			setTestResult(null);
			return;
		}
		const skipPaths = config.skip_paths ?? [];
		for (const glob of skipPaths) {
			if (matchesGlob(path, glob)) {
				setTestResult({ matches: true, glob });
				return;
			}
		}
		setTestResult({ matches: false, glob: null });
	}, [testPathInput, config, matchesGlob]);

	const findNodeByFilterPath = useCallback((root: PathNode, filterPath: string): PathNode | null => {
		if (root.filterPath === filterPath) return root;
		for (const child of root.children.values()) {
			const found = findNodeByFilterPath(child, filterPath);
			if (found) return found;
		}
		return null;
	}, []);

	const handleAddSkipPath = useCallback(() => {
		const path = newSkipPath.trim();
		if (!path) return;
		if (config) {
			const currentSkipPaths = config.skip_paths ?? [];
			if (!currentSkipPaths.includes(path)) {
				setSkipPaths([...currentSkipPaths, path]);
			}
		}
		setNewSkipPath("");
	}, [newSkipPath, config, setSkipPaths]);

	const handleRemoveSkipPath = useCallback((path: string) => {
		if (config) {
			const currentSkipPaths = config.skip_paths ?? [];
			setSkipPaths(currentSkipPaths.filter((p) => p !== path));
		}
	}, [config, setSkipPaths]);

	const skipPathRecommendations = useMemo(() => {
		const candidates: { path: string; eventCount: number }[] = [];
		for (const file of allFiles) {
			const path = file.node.filterPath || file.node.fullPath;
			if (selectedRepoKey !== "all") {
				if (selectedRepoKey === "outside_repo") {
					if (projectTrees.some((p) => path.startsWith(p.repoRoot))) continue;
				} else {
					if (!path.startsWith(selectedRepoKey)) continue;
				}
			}

			if (file.node.eventCount > 0 && file.node.findingCount === 0) {
				candidates.push({
					path,
					eventCount: file.node.eventCount,
				});
			}
		}
		return candidates
			.sort((a, b) => b.eventCount - a.eventCount)
			.slice(0, 4);
	}, [allFiles, selectedRepoKey, projectTrees]);

	const recommendationsCount = skipPathRecommendations.length;

	const repoOptions = useMemo(() => {
		const options: RepoOption[] = [
			{
				key: "all",
				label: "All repositories",
				repoRoot: null,
				mode: "all",
				events: filteredEvents,
				rules: filteredRules,
			},
		];

		for (const repo of projectTrees) {
			options.push({
				key: repo.repoRoot,
				label: repo.projectName,
				repoRoot: repo.repoRoot,
				mode: "repo",
				events: repo.events,
				rules: repo.rules,
				tree: repo.tree,
				sorted: repo.sorted,
			});
		}

		if (nonSlopgateTree) {
			options.push({
				key: "outside_repo",
				label: "Outside enrolled repos",
				repoRoot: null,
				mode: "outside_repo",
				events: nonSlopgateGroup.events,
				rules: nonSlopgateGroup.rules,
				tree: nonSlopgateTree.tree,
				sorted: nonSlopgateTree.sorted,
			});
		}

		return options;
	}, [projectTrees, nonSlopgateTree, filteredEvents, filteredRules, nonSlopgateGroup]);

	const selectedRepo = useMemo(() => {
		return repoOptions.find((opt) => opt.key === selectedRepoKey);
	}, [repoOptions, selectedRepoKey]);

	const treesToRender = useMemo(() => {
		if (selectedRepoKey === "all") return projectTrees;
		if (selectedRepoKey === "outside_repo") return [];
		return projectTrees.filter((p) => p.repoRoot === selectedRepoKey);
	}, [projectTrees, selectedRepoKey]);

	const heatmapEvents = useMemo(() => {
		if (selectedRepoKey === "all") return filteredEvents;
		if (selectedRepoKey === "outside_repo") return nonSlopgateGroup.events;
		return filteredEvents.filter((e) => e.resolved_repo_root === selectedRepoKey);
	}, [filteredEvents, selectedRepoKey, nonSlopgateGroup.events]);

	const heatmapRules = useMemo(() => {
		if (selectedRepoKey === "all") return filteredRules;
		if (selectedRepoKey === "outside_repo") return nonSlopgateGroup.rules;
		return filteredRules.filter((r) => r.resolved_repo_root === selectedRepoKey);
	}, [filteredRules, selectedRepoKey, nonSlopgateGroup.rules]);

	const repoFiles = useMemo(() => {
		const files: PathNode[] = [];
		function collect(node: PathNode) {
			if (node.children.size === 0 && node.eventCount > 0) {
				files.push(node);
			}
			for (const c of node.children.values()) collect(c);
		}

		if (selectedRepoKey === "all") {
			for (const proj of projectTrees) {
				collect(proj.tree);
			}
			if (nonSlopgateTree) collect(nonSlopgateTree.tree);
		} else {
			const activeTree =
				selectedRepoKey === "outside_repo"
					? nonSlopgateTree?.tree
					: projectTrees.find((p) => p.repoRoot === selectedRepoKey)?.tree;
			if (activeTree) collect(activeTree);
		}
		return files;
	}, [selectedRepoKey, projectTrees, nonSlopgateTree]);

	const filesTouchedCount = repoFiles.length;

	const hottestPath = useMemo(() => {
		if (repoFiles.length === 0) return "None";
		const sorted = [...repoFiles].sort((a, b) => b.eventCount - a.eventCount);
		return sorted[0].filterPath || sorted[0].fullPath;
	}, [repoFiles]);

	const repoBlocks = useMemo(() => {
		if (!selectedRepo) return 0;
		return selectedRepo.rules.filter((r) => r.decision === "block" || r.decision === "deny").length;
	}, [selectedRepo]);

	return (
		<div className="space-y-6">
			{/* Page Header */}
			<div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b pb-5">
				<div className="space-y-1">
					<h1 className="text-xl font-bold tracking-tight">Projects & Repositories</h1>
						<p className="text-sm text-muted-foreground">
Path telemetry, repository structure, and skip-path configuration across enrolled repos.
</p>
				</div>
				<div className="flex items-center gap-2">
					<Button
						onClick={() => setIsRuleModalOpen(true)}
						variant="outline"
						className="flex items-center gap-1.5 text-xs h-9"
					>
						<Sparkles className="w-3.5 h-3.5" />
						Draft Rule with Hermes
					</Button>
					{blockedFileCount > 0 && (
						<Badge variant="destructive" className="bg-signal-block text-black/80 flex items-center gap-1 h-6">
							<AlertTriangle className="w-3 h-3" />
							{blockedFileCount} files with blocks
						</Badge>
					)}
				</div>
			</div>

			{/* Main Layout Grid */}
			<div className="grid grid-cols-1 xl:grid-cols-[280px_minmax(0,1fr)] gap-6 items-start">
				
				{/* Sidebar - Mobile Select */}
				<div className="block xl:hidden space-y-1">
					<label htmlFor="repo-select" className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
						Select Repository
					</label>
					<select
						id="repo-select"
						value={selectedRepoKey}
						onChange={(e) => setSelectedRepoKey(e.target.value)}
						className="w-full bg-background border border-input rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
					>
						{repoOptions.map((opt) => (
							<option key={opt.key} value={opt.key ?? "outside_repo"}>
								{opt.label} ({opt.events.length} events)
						</option>
					))}
				</select>
				</div>

				{/* Sidebar - Desktop List */}
				<div className="hidden xl:block">
					<Card>
						<CardHeader className="py-3 px-4 border-b">
							<CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
								Repositories
							</CardTitle>
						</CardHeader>
						<CardContent className="p-2 space-y-1">
							{repoOptions.map((opt) => {
								const isSelected = selectedRepoKey === opt.key;
								const modeStr = opt.mode === "outside_repo" 				? "outside_repo" 				: opt.repoRoot 					? getRepoEnforcementMode(opt.repoRoot) 					: null;
								const blockCount = opt.rules.filter(
									(r) => r.decision === "block" || r.decision === "deny"
								).length;

								return (
									<button
										key={opt.key}
										type="button"
										onClick={() => setSelectedRepoKey(opt.key)}
										className={cn(
											"w-full text-left p-2.5 rounded-md transition-all flex flex-col gap-1 focus:outline-none focus-visible:ring-1 focus-visible:ring-primary",
											isSelected
												? "bg-primary/10 border border-primary/20 text-primary"
												: "hover:bg-muted/60 border border-transparent text-foreground"
										)}
									>
										<div className="flex items-center justify-between w-full">
											<span className="font-semibold text-xs truncate max-w-[150px]">
												{opt.label}
											</span>
											{modeStr && (
												<Badge 				variant="secondary" 				className={cn(
														"text-xs px-1 py-0 scale-90 origin-right font-normal",
														modeStr === "repo_strict" && "bg-signal-block/10 text-signal-block border border-signal-block/20",
														modeStr === "repo_relaxed" && "bg-signal-ask/10 text-signal-ask border border-signal-ask/20",
														modeStr === "outside_repo" && "bg-muted text-muted-foreground"
													)}
												>
													{modeStr}
												</Badge>
											)}
										</div>
										{opt.repoRoot && (
											<span className="text-xs text-muted-foreground/70 font-mono truncate max-w-[240px]">
												{opt.repoRoot}
											</span>
										)}
										<div className="flex items-center gap-1.5 text-xs text-muted-foreground/80 mt-1">
											<span>{opt.events.length} events</span>
											<span>•</span>
											<span>{opt.rules.length} findings</span>
											{blockCount > 0 && (
												<>
													<span>•</span>
													<Badge variant="destructive" className="bg-signal-block text-black/80 text-xs px-1 py-0 scale-95 font-bold">
														{blockCount} blocks
													</Badge>
												</>
											)}
										</div>
									</button>
								);
							})}
						</CardContent>
					</Card>
				</div>

				{/* Main Content Area */}
				<main className="space-y-6">
					{/* Tab Navigation */}
					<div className="flex border-b border-border gap-2">
						{[
							{ key: "overview" as const, label: "Overview", icon: Settings },
							{ key: "telemetry" as const, label: "Files & Paths", icon: FileText },
							{ key: "recommendations" as const, label: "Path Insights", icon: Sparkles },
						].map(({ key, label, icon: Icon }) => (
							<button
								key={key}
								type="button"
								onClick={() => setActiveExplorerTab(key)}
								className={cn(
									"px-4 py-2 text-xs font-medium border-b-2 transition-all flex items-center gap-2 focus:outline-none",
									activeExplorerTab === key
										? "border-primary text-primary"
										: "border-transparent text-muted-foreground hover:text-foreground"
								)}
							>
								<Icon className="w-3.5 h-3.5" />
								{label}
								{key === "recommendations" && recommendationsCount > 0 && (
									<Badge className="ml-1 bg-primary text-primary-foreground text-xs px-1 py-0 h-4 min-w-4 justify-center">
										{recommendationsCount}
									</Badge>
								)}
						</button>
					))}
				</div>

					{/* Tab Panels */}
					{activeExplorerTab === "overview" && (
						<div className="space-y-6 animate-fade-in">
							{/* Repository Overview Card */}
							<Card>
								<CardHeader className="pb-3 border-b">
									<CardTitle className="text-sm font-semibold">Repository Overview</CardTitle>
									<CardDescription className="text-xs">
										Detailed activity statistics and enforcement mode for the selected context.
									</CardDescription>
								</CardHeader>
								<CardContent className="pt-4">
									<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
										<div className="space-y-1">
											<div className="text-xs text-muted-foreground uppercase font-mono">Repository root</div>
											<div className="text-xs font-mono truncate" title={selectedRepo?.repoRoot ?? "All repositories"}>
											</div>
										</div>
										<div className="space-y-1">
											<div className="text-xs text-muted-foreground uppercase font-mono">Enforcement Mode</div>
											<div>
												<Badge 				variant="secondary"
													className={cn(
														"text-xs font-semibold px-2 py-0.5",
														selectedRepo?.mode === "outside_repo" && "bg-muted text-muted-foreground",
														selectedRepo?.mode === "all" && "bg-primary/15 text-primary border border-primary/20",
														selectedRepo?.mode === "repo" && selectedRepo.repoRoot && getRepoEnforcementMode(selectedRepo.repoRoot) === "repo_strict" && "bg-signal-block/15 text-signal-block border border-signal-block/20",
														selectedRepo?.mode === "repo" && selectedRepo.repoRoot && getRepoEnforcementMode(selectedRepo.repoRoot) === "repo_relaxed" && "bg-signal-ask/15 text-signal-ask border border-signal-ask/20"
													)}
												>
													{selectedRepo?.mode === "all" 				? "all_repos" 				: selectedRepo?.mode === "outside_repo" 					? "outside_repo" 					: getRepoEnforcementMode(selectedRepo?.repoRoot ?? "")
													}
												</Badge>
											</div>
										</div>
										<div className="space-y-1">
											<div className="text-xs text-muted-foreground uppercase font-mono">Activity summary</div>
											<div className="text-xs font-medium text-foreground">
												{selectedRepo?.events.length ?? 0} events · {selectedRepo?.rules.length ?? 0} findings · {repoBlocks} blocks
											</div>
										</div>
										<div className="space-y-1">
											<div className="text-xs text-muted-foreground uppercase font-mono">Files & Hot paths</div>
											<div className="text-xs text-foreground font-medium">
												{filesTouchedCount} touched · <span className="font-mono text-xs" title={hottestPath}>{hottestPath.split("/").pop()} (hottest)</span>
											</div>
										</div>
									</div>
								</CardContent>
							</Card>

							{/* Path Settings Card */}
							<Card>
								<CardHeader className="pb-3 border-b">
									<CardTitle className="text-sm font-semibold">Path Settings</CardTitle>
									<CardDescription className="text-xs">
									</CardDescription>
								</CardHeader>
								<CardContent className="pt-4 space-y-6">
									<div className="space-y-2">
										<h4 className="text-xs font-semibold text-foreground uppercase tracking-wider">
											Global skip paths
										</h4>
										<p className="text-xs text-muted-foreground">
									</p>
										
										{/* Skip paths tags list */}
										<div className="flex flex-wrap gap-1.5 pt-1">
											{config?.skip_paths && config.skip_paths.length > 0 ? (
												config.skip_paths.map((path) => (
													<Badge 				key={path} 				variant="secondary"
														className="text-xs font-mono py-1 pl-2.5 pr-1.5 flex items-center gap-1.5"
													>
														{path}
														<button
															type="button"
															onClick={() => handleRemoveSkipPath(path)}
															className="text-muted-foreground hover:text-foreground hover:bg-muted p-0.5 rounded-full focus:outline-none transition-colors"
															aria-label={`Remove glob ${path}`}
														>
															<X className="w-3 h-3" />
														</button>
													</Badge>
												))
											) : (
												<span className="text-xs text-muted-foreground italic">No skip paths configured</span>
											)}
										</div>

										{/* Skip Path Adder */}
										<div className="flex gap-2 max-w-md pt-2">
											<div className="relative flex-1">
												<Input
													id="new-skip-path"
													placeholder="e.g. **/node_modules/**"
													value={newSkipPath}
													onChange={(e) => setNewSkipPath(e.target.value)}
													className="text-xs font-mono h-8"
												/>
											</div>
											<Button
												onClick={handleAddSkipPath}
												variant="outline"
												className="text-xs h-8 px-3 flex items-center gap-1"
											>
												<Plus className="w-3.5 h-3.5" />
												Add Glob
											</Button>
										</div>
									</div>

									{/* Boundary Tester */}
									<div className="border-t pt-4 space-y-3">
										<h4 className="text-xs font-semibold text-foreground uppercase tracking-wider">
											Client-side Path Skip Boundary Tester
										</h4>
										<p className="text-xs text-muted-foreground">
											Test a custom path instantly to see if it would match the configured skip paths and suppress repository-strict enforcement. Test path description
										</p>
										<div className="flex gap-2 max-w-md">
											<div className="relative flex-1">
												<Input
													id="test-path-input"
													placeholder="Enter path to test, e.g. src/index.ts"
													value={testPathInput}
													onChange={(e) => setTestPathInput(e.target.value)}
													className="text-xs font-mono h-8"
												/>
											</div>
											<Button
												onClick={handleTestPath}
												className="text-xs h-8 px-4"
											>
												Test
											</Button>
										</div>

										{testResult !== null && (
											<div className={cn(
												"p-3 rounded-md border text-xs max-w-md animate-fade-in font-mono flex flex-col gap-1",
												testResult.matches 				? "bg-signal-block/5 border-signal-block/20 text-signal-block" 				: "bg-signal-ask/5 border-signal-ask/20 text-signal-ask"
											)}>
												<div className="flex items-center gap-1.5 font-semibold">
													{testResult.matches ? (
														<>
															<CheckCircle2 className="w-4 h-4 text-signal-block" />
															<span>Matches skip paths (Suppressed)</span>
														</>
													) : (
														<>
															<AlertTriangle className="w-4 h-4 text-signal-ask" />
															<span>Does not match skip paths (Enforced)</span>
														</>
													)}
												</div>
												<div className="text-xs text-muted-foreground mt-1">
													{testResult.matches 				? `Suppressed by matching glob: "${testResult.glob}"` 				: "This path will be evaluated by all repository-strict rules."}
												</div>
											</div>
										)}
									</div>

									{/* Save Status and Action bar */}
									{pendingCount > 0 && (
										<div className="border-t pt-4 flex items-center justify-between animate-fade-in">
											<span className="text-xs text-muted-foreground font-medium">
												{pendingCount} unsaved configuration changes
											</span>
											<div className="flex gap-2">
												<Button
													onClick={discardChanges}
													variant="ghost"
													className="text-xs h-8"
												>
													<RotateCcw className="w-3.5 h-3.5 mr-1" />
													Discard
												</Button>
												<Button
													onClick={saveConfig}
													className="text-xs h-8 flex items-center gap-1"
													disabled={saveStatus === "saving"}
												>
													<Save className="w-3.5 h-3.5 mr-1" />
													{saveStatus === "saving" ? "Saving..." : "Save Changes"}
												</Button>
											</div>
										</div>
									)}
									{saveStatus === "error" && saveError && (
										<div className="text-xs text-destructive mt-1 font-mono">
											Failed to save configuration: {saveError}
										</div>
									)}
								</CardContent>
							</Card>
						</div>
					)}

					{activeExplorerTab === "telemetry" && (
						<div className="space-y-4 animate-fade-in">
							{/* Telemetry Inner View Tab switcher */}
							<div className="flex items-center justify-between border-b pb-3">
								<div className="flex gap-1">
									{[
										{ key: "tree" as PathTab, label: "Tree", icon: TreePine },
										{ key: "heatmap" as PathTab, label: "Activity Heatmap", icon: Grid3X3 },
										{ key: "flagged" as PathTab, label: "Flagged Paths", icon: FlagIcon },
									].map(({ key, label, icon: Icon }) => (
										<button
											type="button"
											key={key}
											onClick={() => setTab(key)}
											className={cn(
												"px-3 py-1 text-xs rounded-sm transition-all flex items-center gap-1.5",
												tab === key
													? "bg-secondary text-secondary-foreground font-medium"
													: "text-muted-foreground hover:bg-muted/60"
											)}
										>
											<Icon className="w-3.5 h-3.5" />
											{label}
										</button>
									))}								</div>
								
								{tab === "tree" && (
									<div className="flex items-center gap-2">
										<button
											type="button"
											onClick={() => setExpandOverride((prev) => prev !== true)}
											className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-muted/30 border border-border text-muted-foreground hover:text-foreground transition-colors"
										>
											<ChevronsUpDown className="w-3 h-3" />
											{expandOverride === true ? "Collapse All" : "Expand All"}
										</button>
										{expandOverride !== null && (
											<button
												type="button"
												onClick={() => setExpandOverride(null)}
												className="text-xs px-1.5 py-1 text-muted-foreground hover:text-foreground"
											>
												Reset
											</button>
										)}
									</div>
								)}
							</div>

							{/* Hottest files strip - only on tree tab */}
							{tab === "tree" && allFiles.length > 0 && (
								<div className="space-y-1.5">
									<h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-1">
										Hottest Active Paths
									</h4>
									<div className="flex gap-2 flex-wrap">
										{allFiles.slice(0, 8).map(({ node: f }) => {
											const absolutePath = f.filterPath || f.fullPath;
											const isFiltered = activePathFilter === absolutePath;
											
											// Only recommend skip-path if eventCount > 0 and findingCount === 0
											const isRecommendationCandidate = f.eventCount > 0 && f.findingCount === 0;

											return (
												<div
													key={absolutePath}
													className={cn(
														"rounded-md border p-2 text-left text-xs font-mono transition-all flex flex-col justify-between min-w-[200px] max-w-[260px]",
														isFiltered
															? "border-primary bg-primary/5 text-primary"
															: f.blockCount > 0
																? "border-signal-block/35 bg-signal-block/5 text-signal-block"
																: "border-border bg-card text-foreground"
													)}
												>
													<div>
														<div className="font-semibold truncate" title={f.fullPath}>
															{f.fullPath.split("/").pop() || f.fullPath}
														</div>
														<div className="text-muted-foreground mt-0.5 text-xs truncate" title={f.fullPath}>
															{f.fullPath}
														</div>
														<div className="text-muted-foreground/80 mt-1">
															{f.eventCount} events · {f.findingCount} findings · {f.blockCount} blocks
														</div>
													</div>
													<div className="flex gap-1.5 mt-2 justify-end">
														<Button
															type="button"
															variant="ghost"
															onClick={() => onPathFilter(isFiltered ? null : absolutePath)}
															className="h-5 px-1.5 text-xs hover:text-primary"
														>
															{isFiltered ? "Clear Filter" : "Filter Path"}
														</Button>
														{isRecommendationCandidate && (
															<Button
																type="button"
																variant="outline"
																onClick={() => {
																	if (config) {
																		const currentSkipPaths = config.skip_paths ?? [];
																		if (!currentSkipPaths.includes(absolutePath)) {
																			setSkipPaths([...currentSkipPaths, absolutePath]);
																		}
																	}
																}}
																className="h-5 px-1.5 text-xs hover:text-signal-ask hover:border-signal-ask/30"
															>
																Skip Path
															</Button>
														)}
													</div>
												</div>
											);
										})}
									</div>
								</div>
							)}

							{/* Search input for Tree */}
							{tab === "tree" && (
								<div className="relative max-w-md">
									<Filter className="absolute left-2.5 top-2 w-3.5 h-3.5 text-muted-foreground/60" />
									<input
										id="search-tree"
										type="text"
										placeholder="Search paths, rules, severities, or decisions..."
										value={searchQuery}
										onChange={(e) => setSearchQuery(e.target.value)}
										className="w-full pl-8 pr-8 py-1.5 bg-muted/40 border border-border/85 rounded text-xs focus:outline-none focus:ring-1 focus:ring-primary/50 text-foreground placeholder:text-muted-foreground/50 transition-all font-mono"
									/>
									{searchQuery && (
										<button
											type="button"
											onClick={() => setSearchQuery("")}
											className="absolute right-2.5 top-2 text-muted-foreground/60 hover:text-foreground focus:outline-none"
											aria-label="Clear search query"
										>
											<X className="w-3.5 h-3.5" />
										</button>
									)}
								</div>
							)}

							{tab === "tree" && searchQuery && (
								<div className="flex items-center gap-2 px-3 py-1.5 bg-primary/5 border border-primary/10 rounded text-xs text-muted-foreground animate-fade-in font-mono">
									<span className="text-primary font-semibold">Search result:</span>
									<span>
										{filteredEventsCount} events · {filteredFindingsCount} findings · {filteredBlocksCount} blocks matching "{searchQuery}"
									</span>
									<button
										type="button"
										onClick={() => setSearchQuery("")}
										className="ml-auto hover:text-foreground text-muted-foreground/60 transition-colors focus:outline-none rounded px-1"
									>
										Clear
									</button>
								</div>
							)}

							{/* Tab Telemetry Content Rendering */}
							{tab === "tree" && (
								<div className="space-y-4">
									{treesToRender.map((proj) => (
										<div key={proj.repoRoot} className="space-y-2">
											<div className="flex items-center gap-2 mt-4 px-1">
												<Folder className="w-4 h-4 text-signal-ask" />
												<span className="font-semibold text-xs text-foreground uppercase tracking-wider">
													{proj.projectName}
												</span>
												<span className="text-xs text-muted-foreground font-mono">
													({proj.repoRoot})
												</span>
												<Badge variant="outline" className="text-xs normal-case ml-auto font-mono">
													{proj.events.length} events · {proj.rules.length} findings
												</Badge>
											</div>
											<div className="border border-border rounded-md bg-card/30 overflow-hidden">
												<table className="w-full text-xs">
													<thead>
														<tr className="border-b border-border text-muted-foreground text-xs uppercase font-mono bg-muted/20">
															<th className="px-2 py-2 text-left">
																<button
																	type="button"
																	onClick={() => setSortKey(sortKey === "alpha" ? "name" : "alpha")}
																	className={cn(
																		"flex items-center gap-1 hover:text-foreground focus:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded px-1 py-0.5",
																		(sortKey === "name" || sortKey === "alpha") && "text-primary font-bold"
																	)}
																>
																	Path
																	{(sortKey === "name" || sortKey === "alpha") && (
																		<ArrowUpDown className="w-3 h-3 animate-fade-in" />
																	)}
																</button>
															</th>
															<th className="px-2 py-2 text-right w-24">
																<button
																	type="button"
																	onClick={() => setSortKey("events")}
																	className={cn(
																		"flex items-center justify-end gap-1 w-full hover:text-foreground focus:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded px-1 py-0.5",
																		sortKey === "events" && "text-primary font-bold"
																	)}
																>
																	Events
																	{sortKey === "events" && (
																		<ArrowUpDown className="w-3 h-3 animate-fade-in" />
																	)}
																</button>
															</th>
															<th className="px-2 py-2 text-right w-24">
																<button
																	type="button"
																	onClick={() => setSortKey("findings")}
																	className={cn(
																		"flex items-center justify-end gap-1 w-full hover:text-foreground focus:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded px-1 py-0.5",
																		sortKey === "findings" && "text-primary font-bold"
																	)}
																>
																	Findings
																	{sortKey === "findings" && (
																		<ArrowUpDown className="w-3 h-3 animate-fade-in" />
																	)}
																</button>
															</th>
															<th className="px-2 py-2 text-right w-24">
																<button
																	type="button"
																	onClick={() => setSortKey("blocks")}
																	className={cn(
																		"flex items-center justify-end gap-1 w-full hover:text-foreground focus:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded px-1 py-0.5",
																		sortKey === "blocks" && "text-primary font-bold"
																	)}
																>
																	Blocks
																	{sortKey === "blocks" && (
																		<ArrowUpDown className="w-3 h-3 animate-fade-in" />
																	)}
																</button>
															</th>
															<th className="px-2 py-2 text-center w-24 text-muted-foreground font-normal">Actions</th>
															<th className="px-2 py-2 text-left text-muted-foreground font-normal">Top Rules</th>
														</tr>
													</thead>
													<tbody>
														<TreeRowsList
															sorted={proj.sorted}
															depth={0}
															onPathFilter={onPathFilter}
															activePathFilter={activePathFilter}
															expandOverride={expandOverride}
															sortKey={sortKey}
															repoRoot={proj.repoRoot}
														/>
													</tbody>
												</table>
											</div>
										</div>
									))}

									{treesToRender.length === 0 && selectedRepoKey !== "outside_repo" && (
										<div className="flex items-center justify-center h-24 border border-dashed border-border rounded-md text-xs text-muted-foreground">
											No slopgate project roots found
										</div>
									)}

									{((selectedRepoKey === "all" || selectedRepoKey === "outside_repo") && nonSlopgateTree && nonSlopgateTree.tree.children.size > 0) && (
										<div className="border border-border rounded-md bg-card/10 p-3 mt-4">
											<button
												type="button"
												onClick={() => setNonSlopgateExpanded(!nonSlopgateExpanded)}
												className="w-full flex items-center justify-between text-xs font-semibold text-muted-foreground uppercase tracking-wider"
											>
												<div className="flex items-center gap-2">
													<ChevronDown
														className={cn(
															"w-3.5 h-3.5 transition-transform",
															!nonSlopgateExpanded && "-rotate-90",
														)}
													/>
													<span>Other / Non-Slopgate Triggers</span>
													<Badge variant="outline" className="text-xs ml-2 normal-case font-normal font-mono">
														{nonSlopgateGroup.events.length} events · {nonSlopgateGroup.rules.length} findings
													</Badge>
												</div>
											</button>

											{nonSlopgateExpanded && (
												<div className="mt-3">
													<div className="border border-border rounded-md bg-card/30 overflow-hidden">
														<table className="w-full text-xs">
															<thead>
																<tr className="border-b border-border text-muted-foreground text-xs uppercase font-mono bg-muted/20">
																	<th className="px-2 py-2 text-left">
																		<button
																			type="button"
																			onClick={() => setSortKey(sortKey === "alpha" ? "name" : "alpha")}
																			className={cn(
																				"flex items-center gap-1 hover:text-foreground focus:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded px-1 py-0.5",
																				(sortKey === "name" || sortKey === "alpha") && "text-primary font-bold"
																			)}
																		>
																			Path
																			{(sortKey === "name" || sortKey === "alpha") && (
																				<ArrowUpDown className="w-3 h-3 animate-fade-in" />
																			)}
																		</button>
																	</th>
																	<th className="px-2 py-2 text-right w-24">
																		<button
																			type="button"
																			onClick={() => setSortKey("events")}
																			className={cn(
																				"flex items-center justify-end gap-1 w-full hover:text-foreground focus:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded px-1 py-0.5",
																				sortKey === "events" && "text-primary font-bold"
																			)}
																		>
																			Events
																			{sortKey === "events" && (
																				<ArrowUpDown className="w-3 h-3 animate-fade-in" />
																			)}
																		</button>
																	</th>
																	<th className="px-2 py-2 text-right w-24">
																		<button
																			type="button"
																			onClick={() => setSortKey("findings")}
																			className={cn(
																				"flex items-center justify-end gap-1 w-full hover:text-foreground focus:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded px-1 py-0.5",
																				sortKey === "findings" && "text-primary font-bold"
																			)}
																		>
																			Findings
																			{sortKey === "findings" && (
																				<ArrowUpDown className="w-3 h-3 animate-fade-in" />
																			)}
																		</button>
																	</th>
																	<th className="px-2 py-2 text-right w-24">
																		<button
																			type="button"
																			onClick={() => setSortKey("blocks")}
																			className={cn(
																				"flex items-center justify-end gap-1 w-full hover:text-foreground focus:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded px-1 py-0.5",
																				sortKey === "blocks" && "text-primary font-bold"
																			)}
																		>
																			Blocks
																			{sortKey === "blocks" && (
																				<ArrowUpDown className="w-3 h-3 animate-fade-in" />
																			)}
																		</button>
																	</th>
																	<th className="px-2 py-2 text-center w-24 text-muted-foreground font-normal">Actions</th>
																	<th className="px-2 py-2 text-left text-muted-foreground font-normal">Top Rules</th>
																</tr>
															</thead>
															<tbody>
																<TreeRowsList
																	sorted={nonSlopgateTree.sorted}
																	depth={0}
															onPathFilter={onPathFilter}
																	activePathFilter={activePathFilter}
																	expandOverride={expandOverride}
																	sortKey={sortKey}
																	repoRoot={null}
																/>
															</tbody>
														</table>
													</div>
												</div>
											)}
										</div>
									)}
								</div>
							)}

							{tab === "heatmap" && (
								<div className="border border-border rounded-md bg-card/30 p-3 overflow-hidden">
									<HeatmapView
										events={heatmapEvents}
										rules={heatmapRules}
										onPathFilter={onPathFilter}
										sessionIndex={sessionIndex}
									/>
								</div>
							)}

							{tab === "flagged" && (
								<div className="border border-border rounded-md bg-card/30 p-3">
									<FlaggedItemsPanel />
								</div>
							)}
						</div>
					)}

					{activeExplorerTab === "recommendations" && (
						<div className="space-y-4 animate-fade-in">
							<Card>
								<CardHeader className="pb-3 border-b">
									<CardTitle className="text-sm font-semibold">Path Insights</CardTitle>
									<CardDescription className="text-xs">
										Automated recommendations for optimizing Slopgate rules based on recent session telemetry and execution speed.
									</CardDescription>
								</CardHeader>
								<CardContent className="pt-4 space-y-4">
									<p className="text-xs text-muted-foreground">
										Based on active telemetry, we recommend configuring skip_paths for high-activity paths that have generated zero findings to optimize hook execution speed. Optimize hook speed description
									</p>

									{skipPathRecommendations.length > 0 ? (
										<div className="space-y-2 pt-2">
											{skipPathRecommendations.map((rec) => (
												<div 
													key={rec.path}
													className="p-3 border rounded-md bg-card flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
												>
													<div className="space-y-1">
														<div className="font-semibold font-mono truncate max-w-[450px]" title={rec.path}>
															{rec.path}
														</div>
														<div className="text-xs text-muted-foreground">
															Telemetry: {rec.eventCount} events · 0 findings · 0 blocks
														</div>
													</div>
													<Button
														onClick={() => {
															if (config) {
																const currentSkipPaths = config.skip_paths ?? [];
																if (!currentSkipPaths.includes(rec.path)) {
																	setSkipPaths([...currentSkipPaths, rec.path]);
																}
															}
														}}
														variant="outline"
														className="text-xs h-7 px-2.5 shrink-0 hover:text-signal-ask hover:border-signal-ask/30"
													>
														Add to skip_paths
													</Button>
												</div>
											))}
										</div>
									) : (
										<div className="flex flex-col items-center justify-center h-32 border border-dashed border-border rounded-md text-xs text-muted-foreground p-4 text-center">
											<CheckCircle2 className="w-8 h-8 text-signal-ask mb-2 opacity-80" />
											<span className="font-medium">All active paths appear to have relevant findings or low event volume.</span>
											<span className="text-xs mt-0.5">No skip paths recommended at this time.</span>
										</div>
									)}
								</CardContent>
							</Card>
						</div>
					)}
				</main>
			</div>

			<RuleIterationModal
				isOpen={isRuleModalOpen}
				onClose={() => setIsRuleModalOpen(false)}
				projects={projectGroups}
			/>
		</div>
	);
});
