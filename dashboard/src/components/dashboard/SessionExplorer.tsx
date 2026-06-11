import { Check, ChevronDown, ChevronRight, Copy } from "lucide-react";
import { memo, type ReactNode, useCallback, useMemo, useState } from "react";
import { DECISION_BADGE_STYLE, PLATFORM_BADGE_STYLE } from "@/lib/chartTheme";
import { cn } from "@/lib/utils";
import type {
	Decision,
	HookEvent,
	HookResult,
	Platform,
	RuleFinding,
	SubprocessRun,
} from "@/types/slopgate";
import { FlagButton } from "./FlagButton";
import { SessionTimeline } from "./SessionTimeline";

export interface SessionData {
	id: string;
	platform: Platform;
	eventCount: number;
	tools: string[];
	languages: string[];
	pathCount: number;
	finalOutcome: Decision;
	duration: number;
	events: HookEvent[];
	findings: RuleFinding[];
	results: HookResult[];
	subprocesses: SubprocessRun[];
}

interface Props {
	sessions: SessionData[];
}

type DateRangeFilter = "all" | "1h" | "6h" | "24h" | "7d";

const DATE_RANGE_LABELS: Record<DateRangeFilter, string> = {
	all: "All time",
	"1h": "1h",
	"6h": "6h",
	"24h": "24h",
	"7d": "7d",
};

const DATE_RANGES: DateRangeFilter[] = ["all", "1h", "6h", "24h", "7d"];
const DATE_RANGE_MS: Record<Exclude<DateRangeFilter, "all">, number> = {
	"1h": 60 * 60 * 1000,
	"6h": 6 * 60 * 60 * 1000,
	"24h": 24 * 60 * 60 * 1000,
	"7d": 7 * 24 * 60 * 60 * 1000,
};

function toggleSetValue<T>(selected: Set<T>, value: T): Set<T> {
	const next = new Set(selected);
	if (next.has(value)) next.delete(value);
	else next.add(value);
	return next;
}

function latestSessionTimestamp(session: SessionData): number {
	const timestamps = [
		...session.events.map((event) => event.timestamp),
		...session.findings.map((finding) => finding.timestamp),
		...session.results.map((result) => result.timestamp),
		...session.subprocesses.map((run) => run.timestamp),
	]
		.map((timestamp) => Date.parse(timestamp))
		.filter(Number.isFinite);
	return timestamps.length > 0 ? Math.max(...timestamps) : 0;
}

function matchesDateRange(
	session: SessionData,
	dateRange: DateRangeFilter,
): boolean {
	if (dateRange === "all") return true;
	const latest = latestSessionTimestamp(session);
	return latest > 0 && Date.now() - latest <= DATE_RANGE_MS[dateRange];
}

function matchesSessionFilters(
	session: SessionData,
	selectedOutcomes: Set<Decision>,
	selectedPlatforms: Set<Platform>,
	selectedLanguages: Set<string>,
	dateRange: DateRangeFilter,
): boolean {
	return (
		(selectedOutcomes.size === 0 ||
			selectedOutcomes.has(session.finalOutcome)) &&
		(selectedPlatforms.size === 0 || selectedPlatforms.has(session.platform)) &&
		(selectedLanguages.size === 0 ||
			session.languages.some((language) => selectedLanguages.has(language))) &&
		matchesDateRange(session, dateRange)
	);
}

export function SessionExplorer({ sessions }: Props) {
	const [expanded, setExpanded] = useState<string | null>(null);
	const [copied, setCopied] = useState<string | null>(null);
	const [page, setPage] = useState(0);
	const [openFilterMenu, setOpenFilterMenu] = useState<string | null>(null);
	const [selectedOutcomes, setSelectedOutcomes] = useState<Set<Decision>>(
		() => new Set(),
	);
	const [selectedPlatforms, setSelectedPlatforms] = useState<Set<Platform>>(
		() => new Set(),
	);
	const [selectedLanguages, setSelectedLanguages] = useState<Set<string>>(
		() => new Set(),
	);
	const [dateRange, setDateRange] = useState<DateRangeFilter>("all");
	const perPage = 15;
	const outcomes = useMemo(
		() => [...new Set(sessions.map((session) => session.finalOutcome))].sort(),
		[sessions],
	);
	const platforms = useMemo(
		() => [...new Set(sessions.map((session) => session.platform))].sort(),
		[sessions],
	);
	const languages = useMemo(
		() => [...new Set(sessions.flatMap((session) => session.languages))].sort(),
		[sessions],
	);
	const filteredSessions = useMemo(
		() =>
			sessions.filter((session) =>
				matchesSessionFilters(
					session,
					selectedOutcomes,
					selectedPlatforms,
					selectedLanguages,
					dateRange,
				),
			),
		[
			sessions,
			selectedOutcomes,
			selectedPlatforms,
			selectedLanguages,
			dateRange,
		],
	);
	const paginated = filteredSessions.slice(
		page * perPage,
		(page + 1) * perPage,
	);

	const copyId = useCallback((id: string) => {
		navigator.clipboard.writeText(id);
		setCopied(id);
		setTimeout(() => setCopied(null), 1500);
	}, []);

	const resetSessionPaging = useCallback(() => {
		setPage(0);
		setExpanded(null);
	}, []);

	return (
		<div className="space-y-2">
			<h3 className="px-1 text-xs text-muted-foreground uppercase tracking-wider">
				Session & Tool Explorer
			</h3>
			<div className="border border-border rounded-md bg-card/30 overflow-hidden">
				<div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-border bg-background/25 px-3 py-2 text-[10px]">
					<FilterGroup label="Outcome">
						<MultiSelectMenu
							menuId="outcome"
							openMenuId={openFilterMenu}
							setOpenMenuId={setOpenFilterMenu}
							options={outcomes}
							selected={selectedOutcomes}
							onToggle={(outcome) => {
								setSelectedOutcomes((current) =>
									toggleSetValue(current, outcome),
								);
								resetSessionPaging();
							}}
						/>
					</FilterGroup>
					<FilterGroup label="Platform">
						<MultiSelectMenu
							menuId="platform"
							openMenuId={openFilterMenu}
							setOpenMenuId={setOpenFilterMenu}
							options={platforms}
							selected={selectedPlatforms}
							onToggle={(platform) => {
								setSelectedPlatforms((current) =>
									toggleSetValue(current, platform),
								);
								resetSessionPaging();
							}}
						/>
					</FilterGroup>
					<FilterGroup label="Range">
						{DATE_RANGES.map((range) => (
							<FilterChip
								key={range}
								active={dateRange === range}
								onClick={() => {
									setDateRange(range);
									resetSessionPaging();
								}}
							>
								{DATE_RANGE_LABELS[range]}
							</FilterChip>
						))}
					</FilterGroup>
					<FilterGroup label="Language">
						<MultiSelectMenu
							menuId="language"
							openMenuId={openFilterMenu}
							setOpenMenuId={setOpenFilterMenu}
							options={languages}
							selected={selectedLanguages}
							onToggle={(language) => {
								setSelectedLanguages((current) =>
									toggleSetValue(current, language),
								);
								resetSessionPaging();
							}}
						/>
					</FilterGroup>
				</div>
				<div className="overflow-x-auto">
					<table className="w-full text-xs">
						<thead>
							<tr className="border-b border-border text-muted-foreground">
								<th className="px-3 py-2 text-left w-8" />
								<th className="px-3 py-2 text-left">Session</th>
								<th className="px-3 py-2 text-left">Platform</th>
								<th className="px-3 py-2 text-center">Events</th>
								<th className="px-3 py-2 text-left">Tools</th>
								<th className="px-3 py-2 text-left">Languages</th>
								<th className="px-3 py-2 text-left">Paths</th>
								<th className="px-3 py-2 text-center">Outcome</th>
								<th className="px-3 py-2 text-right">Duration</th>
								<th className="px-3 py-2 w-8" />
							</tr>
						</thead>
						<tbody>
							{paginated.map((s) => (
								<SessionRow
									key={s.id}
									session={s}
									isExpanded={expanded === s.id}
									isCopied={copied === s.id}
									onToggle={() => setExpanded(expanded === s.id ? null : s.id)}
									onCopy={() => copyId(s.id)}
								/>
							))}
							{paginated.length === 0 && (
								<tr>
									<td
										colSpan={10}
										className="px-3 py-6 text-center text-[10px] text-muted-foreground"
									>
										No sessions match the current filter.
									</td>
								</tr>
							)}
						</tbody>
					</table>
				</div>
				<div className="flex items-center justify-between px-3 py-2 border-t border-border text-[10px] text-muted-foreground">
					<span>
						{filteredSessions.length} of {sessions.length} sessions
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
							{page + 1}/
							{Math.max(1, Math.ceil(filteredSessions.length / perPage))}
						</span>
						<button
							type="button"
							disabled={(page + 1) * perPage >= filteredSessions.length}
							onClick={() => setPage((p) => p + 1)}
							className="hover:text-foreground disabled:opacity-30"
						>
							Next →
						</button>
					</div>
				</div>
			</div>
		</div>
	);
}

const SessionRow = memo(function SessionRow({
	session: s,
	isExpanded,
	isCopied,
	onToggle,
	onCopy,
}: {
	session: SessionData;
	isExpanded: boolean;
	isCopied: boolean;
	onToggle: () => void;
	onCopy: () => void;
}) {
	return (
		<>
			<tr
				className={cn(
					"border-b border-border/50 hover:bg-muted/20 cursor-pointer transition-colors",
					isExpanded && "bg-muted/10",
				)}
				onClick={onToggle}
			>
				<td className="px-3 py-2">
					{isExpanded ? (
						<ChevronDown className="w-3 h-3" />
					) : (
						<ChevronRight className="w-3 h-3" />
					)}
				</td>
				<td className="px-3 py-2 font-mono">
					<span className="flex items-center gap-1">
						{s.id.slice(0, 16)}…
						<button
							type="button"
							onClick={(e) => {
								e.stopPropagation();
								onCopy();
							}}
							className="hover:text-primary"
						>
							{isCopied ? (
								<Check className="w-3 h-3" />
							) : (
								<Copy className="w-3 h-3" />
							)}
						</button>
					</span>
				</td>
				<td className="px-3 py-2">
					<span
						className={cn(
							"px-1.5 py-0.5 rounded text-[10px] uppercase",
							PLATFORM_BADGE_STYLE[s.platform],
						)}
					>
						{s.platform}
					</span>
				</td>
				<td className="px-3 py-2 text-center">{s.eventCount}</td>
				<td className="px-3 py-2">
					<div className="flex gap-1 flex-wrap max-w-[200px]">
						{s.tools.slice(0, 4).map((t) => (
							<span
								key={t}
								className="px-1.5 py-0.5 bg-muted rounded text-[10px]"
							>
								{t}
							</span>
						))}
						{s.tools.length > 4 && (
							<span className="text-muted-foreground">
								+{s.tools.length - 4}
							</span>
						)}
					</div>
				</td>
				<td className="px-3 py-2">
					<span className="text-muted-foreground">
						{s.languages.join(", ")}
					</span>
				</td>
				<td className="px-3 py-2">
					<div className="flex gap-1 flex-wrap max-w-[200px]">
						{[...new Set(s.events.flatMap((e) => e.candidate_paths ?? []))]
							.slice(0, 3)
							.map((p) => (
								<span
									key={p}
									className="px-1 py-0.5 bg-muted rounded text-[10px] font-mono truncate max-w-[120px]"
									title={p}
								>
									{p.split("/").pop()}
								</span>
							))}
						{s.pathCount > 3 && (
							<span className="text-muted-foreground text-[10px]">
								+{s.pathCount - 3}
							</span>
						)}
					</div>
				</td>
				<td className="px-3 py-2 text-center">
					<span
						className={cn(
							"px-1.5 py-0.5 rounded border text-[10px] uppercase",
							DECISION_BADGE_STYLE[s.finalOutcome],
						)}
					>
						{s.finalOutcome}
					</span>
				</td>
				<td className="px-3 py-2 text-right text-muted-foreground">
					{s.duration > 60000
						? `${(s.duration / 60000).toFixed(1)}m`
						: `${(s.duration / 1000).toFixed(0)}s`}
				</td>
				<td className="px-3 py-2">
					<FlagButton
						itemType="session"
						itemId={s.id}
						label={`Session ${s.id.slice(0, 12)} (${s.platform}, ${s.finalOutcome})`}
						compact
					/>
				</td>
			</tr>
			{isExpanded && (
				<tr>
					<td colSpan={10} className="max-w-0 overflow-hidden p-0">
						<SessionTimeline session={s} />
					</td>
				</tr>
			)}
		</>
	);
});

function FilterGroup({
	label,
	children,
}: {
	label: string;
	children: ReactNode;
}) {
	return (
		<div className="flex flex-wrap items-center gap-1.5">
			<span className="min-w-14 text-muted-foreground">{label}:</span>
			{children}
		</div>
	);
}

function FilterChip({
	active,
	onClick,
	children,
}: {
	active: boolean;
	onClick: () => void;
	children: ReactNode;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			className={cn(
				"rounded border px-1.5 py-0.5 transition-colors",
				active
					? "border-primary/40 bg-primary/15 text-primary"
					: "border-border/40 bg-muted/20 text-muted-foreground hover:text-foreground",
			)}
		>
			{children}
		</button>
	);
}

function MultiSelectMenu<T extends string>({
	menuId,
	openMenuId,
	setOpenMenuId,
	options,
	selected,
	onToggle,
}: {
	menuId: string;
	openMenuId: string | null;
	setOpenMenuId: (menuId: string | null) => void;
	options: T[];
	selected: Set<T>;
	onToggle: (option: T) => void;
}) {
	const isOpen = openMenuId === menuId;
	const selectionLabel =
		selected.size === 0 ? "All" : `${selected.size} selected`;

	return (
		<div className="relative">
			<button
				type="button"
				onClick={() => setOpenMenuId(isOpen ? null : menuId)}
				className={cn(
					"rounded border px-1.5 py-0.5 transition-colors",
					selected.size > 0 || isOpen
						? "border-primary/40 bg-primary/15 text-primary"
						: "border-border/40 bg-muted/20 text-muted-foreground hover:text-foreground",
				)}
			>
				{selectionLabel}
			</button>
			{isOpen && (
				<div className="absolute left-0 top-full z-30 mt-1 min-w-40 rounded border border-border bg-popover p-2 shadow-lg">
					<div className="mb-1 text-[9px] uppercase tracking-wider text-muted-foreground">
						Options
					</div>
					<div className="max-h-48 space-y-1 overflow-y-auto">
						{options.map((option) => (
							<label
								key={option}
								className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-muted-foreground hover:bg-muted/20 hover:text-foreground"
							>
								<input
									type="checkbox"
									checked={selected.has(option)}
									onChange={() => onToggle(option)}
									className="h-3 w-3 rounded border-border text-primary focus:ring-primary"
								/>
								<span>{option}</span>
							</label>
						))}
					</div>
				</div>
			)}
		</div>
	);
}
