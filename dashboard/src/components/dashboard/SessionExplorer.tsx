import { Check, ChevronDown, ChevronRight, Copy } from "lucide-react";
import {
    memo,
    type ReactNode,
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";
import {
    DECISION_BADGE_STYLE,
    PLATFORM_BADGE_STYLE,
    SEVERITY_TEXT_STYLE,
} from "@/lib/chartTheme";
import type { SessionData } from "@/lib/sessionHelpers";
import {
    primarySessionCause,
    sessionActivitySummary,
} from "@/lib/sessionHelpers";
import { cn } from "@/lib/utils";
import type { Decision, Platform } from "@/types/slopgate";
import { FlagButton } from "./FlagButton";
import { SessionOutcomeSummary } from "./SessionOutcomeSummary";
import { SessionTimeline } from "./SessionTimeline";

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
	let latest = 0;
	const inspectTimestamp = (timestamp: string | undefined) => {
		if (!timestamp) return;
		const parsed = Date.parse(timestamp);
		if (Number.isFinite(parsed) && parsed > latest) latest = parsed;
	};
	for (const event of session.events) inspectTimestamp(event.timestamp);
	for (const finding of session.findings) inspectTimestamp(finding.timestamp);
	for (const result of session.results) inspectTimestamp(result.timestamp);
	for (const run of session.subprocesses) inspectTimestamp(run.timestamp);
	return latest;
}

function uniqueEventCandidatePaths(events: SessionData["events"]): string[] {
	const paths: string[] = [];
	const seen = new Set<string>();
	for (const event of events) {
		for (const path of event.candidate_paths ?? []) {
			if (!path || seen.has(path)) continue;
			seen.add(path);
			paths.push(path);
		}
	}
	return paths;
}

function matchesDateRange(
    session: SessionData,
    dateRange: DateRangeFilter,
): boolean {
    if (dateRange === "all") return true;
    const latest = latestSessionTimestamp(session);
    return latest > 0 && Date.now() - latest <= DATE_RANGE_MS[dateRange];
}

function matchesSearchQuery(session: SessionData, query: string): boolean {
	if (!query.trim()) return true;
	const q = query.toLowerCase().trim();

	// Session ID
	const sessionIds = [
		session.id,
		...(session.rawSessionIds ?? []),
		...(session.childSessions ?? []).map((child) => child.id),
		...(session.mirrorSessions ?? []).map((mirror) => mirror.id),
	];
	if (sessionIds.some((id) => id.toLowerCase().includes(q))) return true;

	// Platform
	if ((session.platforms ?? [session.platform]).some((p) => p.includes(q))) {
		return true;
	}

    // Outcome
    if (session.finalOutcome.toLowerCase().includes(q)) return true;

    // Tool name
    if (session.tools.some((t) => t.toLowerCase().includes(q))) return true;

    // Rule ID
    const hasRuleId =
        session.findings.some((f) => f.rule_id?.toLowerCase().includes(q)) ||
        session.results.some((r) =>
            r.findings.some((f) => f.rule_id?.toLowerCase().includes(q)),
        );
    if (hasRuleId) return true;

    // Candidate paths
    const cause = primarySessionCause(session);
    const causePaths = cause.paths || [];
    const eventCandidatePaths = session.events.flatMap(
        (e) => e.candidate_paths ?? [],
    );
    const allPaths = [...new Set([...causePaths, ...eventCandidatePaths])];
    if (
        allPaths.some((p) => {
            const lowerP = p.toLowerCase();
            const basename = p.split("/").pop() || "";
            return lowerP.includes(q) || basename.toLowerCase().includes(q);
        })
    ) {
        return true;
    }

    // Command text
    const eventCommands = session.events
        .map((e) => e.command)
        .filter((c): c is string => !!c);
    const resultCommands = session.results
        .map((r) => r.command)
        .filter((c): c is string => !!c);
    const subprocessCommands = session.subprocesses
        .map((s) => s.command)
        .filter((c): c is string => !!c);
    const allCommands = [
        ...eventCommands,
        ...resultCommands,
        ...subprocessCommands,
    ];
    if (allCommands.some((c) => c.toLowerCase().includes(q))) return true;

    return false;
}

function matchesSessionFilters(
    session: SessionData,
    selectedOutcomes: Set<Decision>,
    selectedPlatforms: Set<Platform>,
    selectedLanguages: Set<string>,
    dateRange: DateRangeFilter,
    searchQuery: string,
): boolean {
	return (
		(selectedOutcomes.size === 0 ||
			selectedOutcomes.has(session.finalOutcome)) &&
		(selectedPlatforms.size === 0 ||
			(session.platforms ?? [session.platform]).some((platform) =>
				selectedPlatforms.has(platform),
			)) &&
        (selectedLanguages.size === 0 ||
            session.languages.some((language) =>
                selectedLanguages.has(language),
            )) &&
        matchesDateRange(session, dateRange) &&
        matchesSearchQuery(session, searchQuery)
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
    const [searchQuery, setSearchQuery] = useState("");
    const perPage = 15;
    const outcomes = useMemo(
        () =>
            [
                ...new Set(sessions.map((session) => session.finalOutcome)),
            ].sort(),
        [sessions],
    );
	const platforms = useMemo(
		() =>
			[
				...new Set(
					sessions.flatMap((session) => session.platforms ?? [session.platform]),
				),
			].sort(),
		[sessions],
	);
    const languages = useMemo(
        () =>
            [
                ...new Set(sessions.flatMap((session) => session.languages)),
            ].sort(),
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
                    searchQuery,
                ),
            ),
        [
            sessions,
            selectedOutcomes,
            selectedPlatforms,
            selectedLanguages,
            dateRange,
            searchQuery,
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
            <div className="flex flex-wrap items-center justify-between gap-2 px-1">
                <h3 className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">
                    Session & Tool Explorer
                </h3>
                <div className="relative w-full sm:w-72">
                    <input
                        type="text"
                        placeholder="Search sessions..."
                        value={searchQuery}
                        onChange={(e) => {
                            setSearchQuery(e.target.value);
                            resetSessionPaging();
                        }}
                        className="w-full bg-background/50 border border-border rounded px-2.5 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/50"
                    />
                </div>
            </div>
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
                            <tr className="border-b border-border text-muted-foreground select-none">
                                <th className="px-3 py-2 text-left w-8" />
                                <th className="px-3 py-2 text-left">Session</th>
                                <th className="px-3 py-2 text-center">
                                    Outcome
                                </th>
                                <th className="px-3 py-2 text-left">
                                    Primary cause
                                </th>
                                <th className="px-3 py-2 text-left">
                                    Platform
                                </th>
                                <th className="px-3 py-2 text-left">
                                    Agent activity
                                </th>
                                <th className="px-3 py-2 text-left">
                                    Files / paths
                                </th>
                                <th className="px-3 py-2 text-right">
                                    Duration
                                </th>
                                <th className="px-3 py-2 w-8" />
                            </tr>
                        </thead>
                        <tbody>
                            {paginated.map((s, index) => (
                                <SessionRow
                                    key={s.id}
                                    session={s}
                                    isExpanded={expanded === s.id}
                                    isCopied={copied === s.id}
                                    onToggle={() =>
                                        setExpanded(
                                            expanded === s.id ? null : s.id,
                                        )
                                    }
                                    onCopy={() => copyId(s.id)}
                                    index={index}
                                />
                            ))}
                            {paginated.length === 0 && (
                                <tr>
                                    <td
                                        colSpan={9}
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
                            {Math.max(
                                1,
                                Math.ceil(filteredSessions.length / perPage),
                            )}
                        </span>
                        <button
                            type="button"
                            disabled={
                                (page + 1) * perPage >= filteredSessions.length
                            }
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
    index,
}: {
    session: SessionData;
    isExpanded: boolean;
    isCopied: boolean;
    onToggle: () => void;
    onCopy: () => void;
    index: number;
}) {
	const cause = useMemo(() => primarySessionCause(s), [s]);
	const activity = useMemo(() => sessionActivitySummary(s), [s]);

	const causePaths = cause.paths || [];
	const childSessions = s.childSessions ?? [];
	const mirrorSessions = s.mirrorSessions ?? [];
	const childSessionIds = new Set(childSessions.map((session) => session.id));
	const mirrorOnlySessions = mirrorSessions.filter(
		(session) => !childSessionIds.has(session.id),
	);
	const rawSessionIds = s.rawSessionIds ?? [s.id];
	const childMirrorCount = childSessions.filter(
		(session) => session.lineageRole === "child_mirror",
	).length;
	const childOnlyCount = childSessions.length - childMirrorCount;
	const mirrorOnlyCount = mirrorOnlySessions.length;
	const lineageCount = childSessions.length + mirrorOnlySessions.length;
	const genericPaths = useMemo(() => uniqueEventCandidatePaths(s.events), [s.events]);
	const displayPaths = causePaths.length > 0 ? causePaths : genericPaths;

    return (
        <>
            <tr
                className={cn(
                    "border-b border-border/50 hover:bg-muted/20 cursor-pointer transition-all duration-150 animate-in fade-in slide-in-from-bottom-1 fill-mode-both",
                    isExpanded && "bg-muted/10",
                )}
                style={{
                    animationDelay: `${index * 25}ms`,
                    animationFillMode: "both",
                }}
                onClick={onToggle}
            >
                <td className="px-3 py-2">
                    <button
                        type="button"
                        onClick={(e) => {
                            e.stopPropagation();
                            onToggle();
                        }}
                        aria-expanded={isExpanded}
                        aria-label={isExpanded ? "Collapse session" : "Expand session"}
                        className="flex items-center justify-center p-1 rounded hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus:ring-1 focus:ring-primary"
                    >
                        {isExpanded ? (
                            <ChevronDown className="w-3.5 h-3.5" />
                        ) : (
                            <ChevronRight className="w-3.5 h-3.5" />
                        )}
                    </button>
                </td>
				<td className="px-3 py-2 font-mono">
					<span className="flex items-center gap-1">
						{s.id.slice(0, 16)}…
						{lineageCount > 0 && (
							<span className="rounded border border-primary/30 bg-primary/10 px-1 py-0.5 text-[9px] font-sans uppercase text-primary">
								+{lineageCount} linked
							</span>
						)}
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
                <td className="px-3 py-2 text-center">
                    <span
                        className={cn(
                            "px-1.5 py-0.5 rounded border text-[10px] uppercase font-bold",
                            DECISION_BADGE_STYLE[s.finalOutcome],
                        )}
                    >
                        {s.finalOutcome}
                    </span>
                </td>
                <td
                    className="px-3 py-2 truncate max-w-[200px]"
                    title={cause.message || ""}
                >
                    {cause.decision === "allow" ? (
                        <span className="text-signal-allow font-medium text-[10px]">
                            Clean allow
                        </span>
                    ) : (
                        <span className="flex items-center gap-1 text-[10px] truncate">
                            {cause.severity && (
                                <span
                                    className={cn(
                                        "font-bold",
                                        SEVERITY_TEXT_STYLE[cause.severity],
                                    )}
                                >
                                    [{cause.severity}]
                                </span>
                            )}
                            {cause.ruleId && (
                                <strong className="text-foreground">
                                    {cause.ruleId}:{" "}
                                </strong>
                            )}
                            <span className="text-muted-foreground truncate">
                                {cause.message}
                            </span>
                        </span>
                    )}
                </td>
				<td className="px-3 py-2">
					<div className="flex flex-wrap gap-1">
						{(s.platforms ?? [s.platform]).map((platform) => (
							<span
								key={platform}
								className={cn(
									"px-1.5 py-0.5 rounded text-[10px] uppercase font-medium",
									PLATFORM_BADGE_STYLE[platform],
								)}
							>
								{platform}
							</span>
						))}
					</div>
				</td>
                <td className="px-3 py-2">
                    <div className="flex items-center gap-1 select-none">
                        {activity.lastTool ? (
                            <span className="px-1.5 py-0.5 bg-muted rounded text-[10px] font-medium text-foreground">
                                {activity.lastTool}
                            </span>
                        ) : (
                            <span className="text-muted-foreground text-[10px] italic">
                                None
                            </span>
                        )}
                        {activity.toolCount > 1 && (
                            <span className="text-muted-foreground text-[10px] font-semibold">
                                +{activity.toolCount - 1}
                            </span>
                        )}
                    </div>
                </td>
                <td className="px-3 py-2">
                    <div className="flex gap-1 flex-wrap max-w-[200px]">
                        {displayPaths.slice(0, 3).map((p) => (
                            <span
                                key={p}
                                className={cn(
                                    "px-1 py-0.5 bg-muted rounded text-[10px] font-mono truncate max-w-[120px]",
                                    causePaths.includes(p) &&
                                        "border border-primary/20 bg-primary/5 text-primary",
                                )}
                                title={p}
                            >
                                {p.split("/").pop()}
                            </span>
                        ))}
                        {displayPaths.length > 3 && (
                            <span className="text-muted-foreground text-[10px]">
                                +{displayPaths.length - 3}
                            </span>
                        )}
                    </div>
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
					<td colSpan={9} className="max-w-0 overflow-hidden p-0">
						{(lineageCount > 0 || (s.rawSessionIds ?? []).length > 1) && (
							<div className="border-b border-border bg-background/40 px-4 py-3 text-[10px] text-muted-foreground">
								<div className="flex flex-wrap items-center gap-2">
									<span className="font-semibold uppercase tracking-wide text-foreground">
										Lineage
									</span>
									<span className="rounded border border-border/40 bg-muted/20 px-1.5 py-0.5">
										{s.lineageConfidence ?? "none"}
									</span>
									{rawSessionIds.length > 1 && (
										<span className="rounded border border-primary/30 bg-primary/10 px-1.5 py-0.5 text-primary">
											{rawSessionIds.length} grouped sessions
										</span>
									)}
									{childOnlyCount > 0 && (
										<span className="rounded border border-border/40 bg-muted/20 px-1.5 py-0.5">
											{childOnlyCount} child
										</span>
									)}
									{childMirrorCount > 0 && (
										<span className="rounded border border-border/40 bg-muted/20 px-1.5 py-0.5">
											{childMirrorCount} child + mirror
										</span>
									)}
									{mirrorOnlyCount > 0 && (
										<span className="rounded border border-border/40 bg-muted/20 px-1.5 py-0.5">
											{mirrorOnlyCount} mirror
										</span>
									)}
								</div>
							</div>
						)}
						<SessionOutcomeSummary session={s} />
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
    const triggerRef = useRef<HTMLButtonElement>(null);

    useEffect(() => {
        if (!isOpen) return;
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                setOpenMenuId(null);
                triggerRef.current?.focus();
            }
        };
        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, [isOpen, setOpenMenuId]);

    return (
        <div className="relative">
            <button
                type="button"
                ref={triggerRef}
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
